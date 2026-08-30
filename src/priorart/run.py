"""End to end: patent number in, claim chart out.

    python -m priorart.run 7240025 --candidates 200

Local runner. The deployed version distributes the screening stage across Cloud
Run Jobs, each task claiming a modulo slice of the candidate table, using the
same `screen` unit of work so the two paths cannot drift apart.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import corpus, judge, search


def run(
    target_id: str,
    n_candidates: int = 200,
    scope: str = "G06Q",
    blind: bool = True,
    out_dir: str = "runs",
) -> dict:
    started = time.time()

    print(f"target {target_id}", file=sys.stderr)
    target = corpus.get_target(target_id, scope)
    print(f"  {target.title}", file=sys.stderr)

    gc = judge.client()
    limitations = judge.split_claim(target.claim_1, gc)
    print(f"  claim 1 split into {len(limitations)} limitations", file=sys.stderr)

    res = search.retrieve(target_id, n_candidates, scope)
    print(
        f"  corpus {res.corpus_size:,} -> "
        f"{res.dropped_not_prior_art:,} not prior art -> "
        f"{res.dropped_same_family:,} same family -> "
        f"{res.eligible:,} eligible -> {len(res.candidates):,} screened",
        file=sys.stderr,
    )

    seen = {"n": 0, "hits": 0}

    def progress(v: judge.Verdict) -> None:
        seen["n"] += 1
        if v.relevant:
            seen["hits"] += 1
            print(
                f"    [{seen['n']:>4}] {v.patent_id}  "
                f"{len(v.limitations_disclosed)} lim  {v.title[:50]}",
                file=sys.stderr,
            )

    verdicts = judge.screen_all(res.candidates, limitations, blind, on_result=progress)

    relevant = sorted(
        [v for v in verdicts if v.relevant],
        key=lambda v: len(v.limitations_disclosed),
        reverse=True,
    )
    tokens_in = sum(v.tokens_in for v in verdicts)
    tokens_out = sum(v.tokens_out for v in verdicts)

    # Chart only the strongest references. Charting reads far more text per
    # candidate, so it is reserved for what screening actually surfaced.
    by_id = {c.patent_id: c for c in res.candidates}
    for v in relevant[:3]:
        v.mappings = judge.chart(by_id[v.patent_id], limitations, gc)

    elapsed = time.time() - started
    # Gemini 3.5 Flash list price, USD per million tokens.
    cost = tokens_in / 1e6 * 1.50 + tokens_out / 1e6 * 9.00

    report = {
        "target": {
            "patent_id": target.patent_id,
            "title": target.title,
            "grant_date": target.grant_date,
            "priority_date": res.target_priority,
            "n_claims": len(target.claims),
        },
        "limitations": [{"index": l.index, "text": l.text} for l in limitations],
        "funnel": {
            "corpus": res.corpus_size,
            "dropped_not_prior_art": res.dropped_not_prior_art,
            "dropped_same_family": res.dropped_same_family,
            "eligible": res.eligible,
            "screened": len(res.candidates),
            "relevant": len(relevant),
        },
        "cost": {
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "usd": round(cost, 4),
            "seconds": round(elapsed, 1),
        },
        "blind": blind,
        "model": judge.MODEL,
        "results": [
            {
                "patent_id": v.patent_id,
                "title": v.title,
                "filing_date": v.filing_date,
                "limitations_disclosed": v.limitations_disclosed,
                "summary": v.summary,
                "mappings": [
                    {
                        "limitation": m.limitation,
                        "discloses": m.discloses,
                        "mapped_text": m.mapped_text,
                        "reasoning": m.reasoning,
                    }
                    for m in v.mappings
                ],
            }
            for v in relevant
        ],
    }

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"{target_id}-{int(started)}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {path}", file=sys.stderr)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a prior-art search")
    ap.add_argument("target")
    ap.add_argument("--candidates", type=int, default=200)
    ap.add_argument("--scope", default="G06Q")
    ap.add_argument(
        "--unblind",
        action="store_true",
        help="show the model each reference's identity (default is blinded)",
    )
    args = ap.parse_args()

    r = run(args.target, args.candidates, args.scope, blind=not args.unblind)

    f = r["funnel"]
    c = r["cost"]
    print("\n" + "=" * 62)
    print(f"{r['target']['patent_id']}  {r['target']['title'][:48]}")
    print(f"priority {r['target']['priority_date']}   {len(r['limitations'])} limitations")
    print("=" * 62)
    print(f"screened {f['screened']:,} of {f['eligible']:,} eligible")
    print(f"relevant {f['relevant']}")
    print(f"{c['seconds']}s   ${c['usd']}   {c['tokens_in']:,} in / {c['tokens_out']:,} out")
    print()
    for hit in r["results"][:5]:
        print(f"  US {hit['patent_id']}  {hit['filing_date']}  "
              f"{len(hit['limitations_disclosed'])} limitations")
        print(f"     {hit['title'][:64]}")
        print(f"     {hit['summary'][:150]}")


if __name__ == "__main__":
    main()
