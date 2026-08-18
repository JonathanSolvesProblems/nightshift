"""Diagnose the judgment stage against a known-good pair.

Takes a (target, reference) pair the USPTO examiner actually applied as a
category-X anticipation rejection, and asks the screener about it directly.

If the model says "not relevant" here, the prompt or the input text is wrong.
If it says relevant, then a zero-hit run means retrieval did not surface good
art, which is a different problem with a different fix.

    python scripts/diagnose_judge.py 10002398 8433650
"""

import sys
from dataclasses import dataclass

from google.cloud import bigquery

sys.path.insert(0, "src")

from priorart import config, judge  # noqa: E402


@dataclass
class Ref:
    patent_id: str
    title: str
    filing_date: str
    disclosure: str


def fetch(client, patent_id: str):
    sql = f"""
    SELECT patent_id, title, grant_date, claims, disclosure
    FROM `{config.working_table("patents_g06q_clustered")}`
    WHERE patent_id = @pid
    """
    rows = list(
        client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("pid", "STRING", patent_id)
                ]
            ),
        ).result()
    )
    return rows[0] if rows else None


def main() -> int:
    target_id, ref_id = sys.argv[1], sys.argv[2]
    client = bigquery.Client(project=config.PROJECT_ID)

    t = fetch(client, target_id)
    r = fetch(client, ref_id)
    if not t or not r:
        print("target or reference missing from corpus", file=sys.stderr)
        return 1

    print(f"TARGET    US {target_id}  {t['title']}")
    print(f"REFERENCE US {ref_id}  {r['title']}")
    print(f"reference disclosure: {len(r['disclosure'] or '')} chars")
    print(f"examiner applied this as a category-X anticipation rejection\n")

    gc = judge.client()
    claim1 = (t["claims"] or [""])[0]
    print(f"claim 1: {len(claim1)} chars")

    lims = judge.split_claim(claim1, gc)
    print(f"split into {len(lims)} limitations:")
    for l in lims:
        print(f"  [{l.index}] {l.text[:95]}")
    print()

    ref = Ref(ref_id, r["title"] or "", str(r["grant_date"]), r["disclosure"] or "")

    for blind in (True, False):
        v = judge.screen(ref, lims, gc, blind=blind)
        label = "blinded" if blind else "unblinded"
        print(f"--- {label} ---")
        print(f"  relevant   {v.relevant}")
        print(f"  disclosed  {v.limitations_disclosed}")
        print(f"  summary    {v.summary[:300]}")
        print(f"  tokens     {v.tokens_in} in / {v.tokens_out} out\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
