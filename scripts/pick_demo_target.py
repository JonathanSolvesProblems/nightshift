"""Choose the demo case on evidence rather than on how it looks.

A demo target is only worth showing if three things are true at once:

  1. A USPTO examiner applied a reference against it as category X, meaning the
     examiner considered that reference to anticipate. That makes the demo a case
     where the agent re-finds a documented answer rather than an opinion.
  2. That reference sits deep enough in the ranking that top-50 retrieval would
     miss it, because depth is the product's whole argument.
  3. The claim chart against it actually produces FULL rows. An all-PARTIAL chart
     is honest and unpersuasive, and picking a target without checking this is
     how a demo ends up technically correct and flat.

Nothing here is seeded. Every candidate is a real gold pair and every chart is a
real model call against real disclosure text.

    python scripts/pick_demo_target.py --pairs 14
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, "src")

from priorart import config, judge  # noqa: E402

# Rank of the examiner's reference among everything that is eligible prior art
# for that target, computed for many pairs in one pass.
RANK_SQL = """
WITH pairs AS (
  SELECT g.target, g.ref
  FROM `{gold}` g
  JOIN `{patents}` t ON t.patent_id = g.target
  JOIN `{patents}` r ON r.patent_id = g.ref
  WHERE g.cat = 'X'
    AND ARRAY_LENGTH(t.claims) > 0
    AND LENGTH(r.disclosure) > 3000
  ORDER BY FARM_FINGERPRINT(CONCAT(g.target, g.ref))
  LIMIT @pairs
),
tv AS (
  SELECT p.target, v.embedding_v1 AS tvec, d.priority_date
  FROM pairs p
  JOIN `{vectors}` v ON v.patent_id = p.target
  JOIN `{dates}` d ON d.patent_id = p.target
),
gold AS (
  SELECT p.target, p.ref,
         ML.DISTANCE(tv.tvec, vr.embedding_v1, 'COSINE') AS gold_dist,
         tv.tvec, tv.priority_date
  FROM pairs p
  JOIN tv ON tv.target = p.target
  JOIN `{vectors}` vr ON vr.patent_id = p.ref
)
SELECT
  g.target, g.ref,
  COUNTIF(ML.DISTANCE(g.tvec, c.embedding_v1, 'COSINE') < g.gold_dist
          AND d.filing_date < g.priority_date) AS rank_pos,
  COUNTIF(d.filing_date < g.priority_date) AS eligible
FROM gold g
CROSS JOIN `{vectors}` c
JOIN `{dates}` d ON d.patent_id = c.patent_id
GROUP BY g.target, g.ref
ORDER BY rank_pos
"""


@dataclass
class Ref:
    patent_id: str
    title: str
    filing_date: str
    disclosure: str


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=14)
    ap.add_argument("--max-rank", type=int, default=6000)
    ap.add_argument("--out", default="eval/demo-candidates.json")
    args = ap.parse_args()

    client = bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)
    sql = RANK_SQL.format(
        gold=config.working_table("gold_pairs"),
        patents=config.working_table("patents_g06q_clustered"),
        vectors=config.working_table("vectors_g06q"),
        dates=config.working_table("dates_g06q"),
    )
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("pairs", "INT64", args.pairs)]
        ),
    )
    ranked = [dict(r) for r in job.result()]
    print(f"ranked {len(ranked)} gold X pairs "
          f"({job.total_bytes_billed / 1024**2:.0f} MB)", file=sys.stderr)

    ids = sorted({r["target"] for r in ranked} | {r["ref"] for r in ranked})
    texts = client.query(
        f"""SELECT patent_id, title, grant_date, claims, disclosure
            FROM `{config.working_table("patents_g06q_clustered")}`
            WHERE patent_id IN UNNEST(@ids)""",
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("ids", "STRING", ids)]
        ),
    ).result()
    text = {
        t["patent_id"]: {
            "title": t["title"] or "",
            "grant_date": str(t["grant_date"]),
            "claims": list(t["claims"] or []),
            "disclosure": t["disclosure"] or "",
        }
        for t in texts
    }

    gc = judge.client()
    results = []

    for row in ranked:
        tgt, ref_id, rank = row["target"], row["ref"], row["rank_pos"]
        if rank > args.max_rank or tgt not in text or ref_id not in text:
            continue
        claim1 = (text[tgt]["claims"] or [""])[0]
        if not claim1 or len(claim1) < 200:
            continue

        try:
            lims = judge.split_claim(claim1, gc)
            t = text[ref_id]
            mappings = judge.chart(
                Ref(ref_id, t["title"], t["grant_date"], t["disclosure"]), lims, gc
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  {tgt} <- {ref_id}: failed {type(exc).__name__}", file=sys.stderr)
            continue

        full = sum(1 for m in mappings if m.level == "FULL")
        partial = sum(1 for m in mappings if m.level == "PARTIAL")
        rec = {
            "target": tgt,
            "target_title": text[tgt]["title"],
            "ref": ref_id,
            "ref_title": text[ref_id]["title"],
            "rank": rank,
            "eligible": row["eligible"],
            "limitations": len(mappings),
            "full": full,
            "partial": partial,
            "absent": len(mappings) - full - partial,
        }
        results.append(rec)
        print(
            f"  US {tgt} <- US {ref_id}  rank {rank:>6,}/{row['eligible']:,}  "
            f"FULL {full}/{len(mappings)}  PARTIAL {partial}",
            file=sys.stderr,
        )

    # Rank demo cases by how much of the claim is actually taught, then by depth,
    # because a deep find is the argument but only if the chart carries it.
    results.sort(key=lambda r: (r["full"], r["full"] + r["partial"], r["rank"]), reverse=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\n" + "=" * 74)
    print("DEMO CANDIDATES, best first")
    print("=" * 74)
    for r in results[:6]:
        print(f"  US {r['target']}  <- US {r['ref']}")
        print(f"     {r['target_title'][:64]}")
        print(f"     depth {r['rank']:,} of {r['eligible']:,} eligible   "
              f"FULL {r['full']}  PARTIAL {r['partial']}  ABSENT {r['absent']}")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
