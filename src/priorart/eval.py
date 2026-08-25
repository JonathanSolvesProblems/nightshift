"""Measure accuracy against references USPTO examiners actually applied.

The eval is decomposed rather than end-to-end, for a reason that is economic and
also makes the result more informative.

A full run screens thousands of candidates per target, so measuring end-to-end
recall over n targets would cost roughly n x $43. Decomposed:

    end-to-end recall @K  =  prefilter recall @K  x  screening recall

Prefilter recall is measured exactly in BigQuery over the whole gold set, for
free (scripts/gate_recall.sql). Screening recall needs one model call per gold
pair instead of thousands, so it costs about $2 rather than $1,290. The two
numbers multiply, and a reader can see which stage loses what.

A negative control runs alongside. Screening recall on its own is trivially
gamed by returning "relevant" for everything, so the same screener is run over
random eligible references the examiner did NOT cite. The gap between the two
rates is the result; either number alone is not.

    python -m priorart.eval --n 40 --out ACCURACY-run.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import sys
import time
from dataclasses import dataclass

from google.cloud import bigquery

from . import config, judge


@dataclass
class Pair:
    target: str
    ref: str
    cat: str
    is_gold: bool


# Gold pairs, plus random eligible non-cited references from the same corpus as
# a negative control. The control is drawn from patents that pass the same
# priority-date gate, so it is a fair comparison rather than an easy one.
SAMPLE_SQL = """
WITH gold AS (
  SELECT target, ref, cat
  FROM `{gold}`
  WHERE cat = @cat
  ORDER BY FARM_FINGERPRINT(CONCAT(target, ref, @seed))
  LIMIT @n
),
targets AS (
  SELECT DISTINCT target FROM gold
),
controls AS (
  SELECT
    t.target,
    p.patent_id AS ref,
    'CONTROL' AS cat
  FROM targets t
  JOIN `{dates}` td ON td.patent_id = t.target
  JOIN `{patents}` p ON TRUE
  JOIN `{dates}` d ON d.patent_id = p.patent_id
  WHERE d.filing_date < td.priority_date
    AND ARRAY_LENGTH(p.claims) > 0
    AND p.patent_id NOT IN (SELECT ref FROM `{gold}` WHERE target = t.target)
    AND p.patent_id != t.target
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY t.target
    ORDER BY FARM_FINGERPRINT(CONCAT(p.patent_id, @seed))
  ) = 1
)
SELECT target, ref, cat FROM gold
UNION ALL
SELECT target, ref, cat FROM controls
"""


def load_sample(cat: str, n: int, seed: str) -> list[Pair]:
    client = bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)
    sql = SAMPLE_SQL.format(
        gold=config.working_table("gold_pairs"),
        dates=config.working_table("dates_g06q"),
        patents=config.working_table("patents_g06q_clustered"),
    )
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("cat", "STRING", cat),
                bigquery.ScalarQueryParameter("n", "INT64", n),
                bigquery.ScalarQueryParameter("seed", "STRING", seed),
            ]
        ),
    )
    rows = list(job.result())
    print(f"  sample scan {job.total_bytes_billed / 1024**2:.0f} MB", file=sys.stderr)
    return [
        Pair(r["target"], r["ref"], r["cat"], r["cat"] != "CONTROL") for r in rows
    ]


def load_texts(ids: list[str]) -> dict:
    """One fetch for every patent the run touches."""
    client = bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)
    sql = f"""
    SELECT patent_id, title, grant_date, claims, disclosure
    FROM `{config.working_table("patents_g06q_clustered")}`
    WHERE patent_id IN UNNEST(@ids)
    """
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", ids)]
        ),
    )
    out = {}
    for r in job.result():
        out[r["patent_id"]] = {
            "title": r["title"] or "",
            "grant_date": str(r["grant_date"]),
            "claims": list(r["claims"] or []),
            "disclosure": r["disclosure"] or "",
        }
    print(f"  text scan {job.total_bytes_billed / 1024**2:.0f} MB", file=sys.stderr)
    return out


@dataclass
class Ref:
    patent_id: str
    title: str
    filing_date: str
    disclosure: str


def run_eval(n: int, seed: str, cats: tuple[str, ...], workers: int) -> dict:
    started = time.time()

    pairs: list[Pair] = []
    for cat in cats:
        pairs.extend(load_sample(cat, n, seed))
    if not pairs:
        raise RuntimeError("no pairs sampled")

    ids = sorted({p.target for p in pairs} | {p.ref for p in pairs})
    texts = load_texts(ids)
    pairs = [p for p in pairs if p.target in texts and p.ref in texts]
    print(f"  {len(pairs)} pairs over {len({p.target for p in pairs})} targets",
          file=sys.stderr)

    gc = judge.client()

    # Claim decomposition is per target, so it is done once and reused across
    # that target's gold pair and its control.
    limits: dict[str, list] = {}
    for t in sorted({p.target for p in pairs}):
        claim1 = (texts[t]["claims"] or [""])[0]
        if not claim1:
            continue
        try:
            limits[t] = judge.split_claim(claim1, gc)
        except Exception as exc:  # noqa: BLE001
            print(f"  split failed {t}: {exc}", file=sys.stderr)
    print(f"  split {len(limits)} target claims", file=sys.stderr)

    pairs = [p for p in pairs if p.target in limits]
    results = []

    def one(p: Pair) -> dict:
        r = texts[p.ref]
        ref = Ref(p.ref, r["title"], r["grant_date"], r["disclosure"])
        # Blinded: the model never sees the reference's identity.
        v = judge.screen(ref, limits[p.target], gc, blind=True)
        return {
            "target": p.target,
            "ref": p.ref,
            "cat": p.cat,
            "is_gold": p.is_gold,
            "found": v.relevant,
            "relevance": v.relevance,
            "n_limitations": len(v.limitations_disclosed),
            "tokens_in": v.tokens_in,
            "tokens_out": v.tokens_out,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, p) for p in pairs]
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                print(f"  screen failed: {exc}", file=sys.stderr)
            if i % 20 == 0:
                print(f"  {i}/{len(futures)}", file=sys.stderr)

    def rate(rows):
        return round(100 * sum(r["found"] for r in rows) / len(rows), 1) if rows else None

    by_cat = {}
    for cat in set(r["cat"] for r in results):
        rows = [r for r in results if r["cat"] == cat]
        by_cat[cat] = {"n": len(rows), "found_rate": rate(rows)}

    tokens_in = sum(r["tokens_in"] for r in results)
    tokens_out = sum(r["tokens_out"] for r in results)

    return {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": judge.MODEL,
        "blinded": True,
        "seed": seed,
        "by_category": by_cat,
        "cost": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "usd": round(tokens_in / 1e6 * 1.50 + tokens_out / 1e6 * 9.00, 3),
            "seconds": round(time.time() - started, 1),
        },
        "results": results,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Measure screening accuracy")
    ap.add_argument("--n", type=int, default=40, help="gold pairs per category")
    ap.add_argument("--seed", default="nightshift-2026-08-25")
    ap.add_argument("--cats", default="X,Y")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--out", default="eval/screening.json")
    args = ap.parse_args()

    report = run_eval(args.n, args.seed, tuple(args.cats.split(",")), args.workers)

    from pathlib import Path

    p = Path(args.out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 58)
    print("SCREENING ACCURACY (blinded)")
    print("=" * 58)
    for cat, v in sorted(report["by_category"].items()):
        label = {"X": "X  examiner anticipation", "Y": "Y  examiner obviousness",
                 "CONTROL": "control  not cited"}.get(cat, cat)
        print(f"  {label:28} n={v['n']:<4} flagged {v['found_rate']}%")
    c = report["cost"]
    print(f"\n  ${c['usd']}   {c['seconds']}s   {c['tokens_in']:,} in / {c['tokens_out']:,} out")
    print(f"  wrote {p}")


if __name__ == "__main__":
    main()
