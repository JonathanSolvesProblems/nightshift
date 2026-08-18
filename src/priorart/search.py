"""Candidate retrieval: the coarse pass in front of the judgment stage.

This stage is not asked to be right. It is asked not to lose the answer.

Measured recall against references a USPTO examiner applied in a rejection,
out of 171,695 corpus patents (see ACCURACY.md):

    category X (anticipation)  78.2% @10k    median rank 1,230
    category Y (obviousness)   66.3% @10k    median rank 3,961

The embedding is 64 dimensions, far too coarse to rank prior art precisely, and
entirely adequate as a high-recall funnel in front of a model that reads what
survives. That trade is the architecture.

Two hard filters run before ranking is ever considered:

1. Prior-art eligibility. Under 35 USC 102 a reference must predate the target's
   earliest priority date. 52.8% of corpus patents claim priority earlier than
   their own filing date, so neither grant date nor filing date alone is correct.
2. Family exclusion. A patent's own continuations and divisionals share its
   disclosure and are not useful prior art against it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

from google.cloud import bigquery

from . import config


@dataclass
class Candidate:
    patent_id: str
    title: str
    distance: float
    filing_date: str
    priority_date: str
    grant_date: str
    disclosure: str


@dataclass
class SearchResult:
    target: str
    target_priority: str
    candidates: list[Candidate] = field(default_factory=list)
    corpus_size: int = 0
    dropped_not_prior_art: int = 0
    dropped_same_family: int = 0

    @property
    def eligible(self) -> int:
        return self.corpus_size - self.dropped_not_prior_art - self.dropped_same_family


# The funnel counts and the ranked candidates run as two queries on purpose.
# Computing both at once needs COUNT(*) OVER (), which forces all 171,695 rows
# plus their disclosure text into a single window partition and exceeds the
# query memory limit. The aggregate below never touches the disclosure column.
TARGET_CTE = """
WITH t AS (
  SELECT
    v.embedding_v1 AS tvec,
    d.priority_date AS t_priority,
    p.title AS t_title
  FROM `{vectors}` v
  JOIN `{dates}` d ON d.patent_id = v.patent_id
  JOIN `{patents}` p ON p.patent_id = v.patent_id
  WHERE v.patent_id = @target
)
"""

FUNNEL_COUNTS_SQL = TARGET_CTE + """
SELECT
  COUNT(*) AS corpus_size,
  COUNTIF(d.filing_date >= t.t_priority) AS dropped_not_prior_art,
  COUNTIF(
    d.filing_date < t.t_priority
    AND (p.title = t.t_title OR d.priority_date = t.t_priority)
  ) AS dropped_same_family,
  ANY_VALUE(t.t_priority) AS target_priority
FROM t, `{vectors}` c
JOIN `{dates}` d ON d.patent_id = c.patent_id
JOIN `{patents}` p ON p.patent_id = c.patent_id
WHERE c.patent_id != @target
"""

CANDIDATES_SQL = TARGET_CTE + """
SELECT
  c.patent_id,
  p.title,
  p.grant_date,
  p.disclosure,
  d.filing_date,
  d.priority_date,
  ML.DISTANCE(t.tvec, c.embedding_v1, 'COSINE') AS distance
FROM t, `{vectors}` c
JOIN `{dates}` d ON d.patent_id = c.patent_id
JOIN `{patents}` p ON p.patent_id = c.patent_id
WHERE c.patent_id != @target
  -- not prior art unless it was on file before the target's priority date
  AND d.filing_date < t.t_priority
  -- same disclosure family: shared title or shared priority date
  AND NOT (p.title = t.t_title OR d.priority_date = t.t_priority)
ORDER BY distance
LIMIT @topn
"""


def retrieve(target: str, top_n: int = 2000, scope: str = "G06Q") -> SearchResult:
    """Rank eligible prior art by similarity to the target patent.

    The query vector is the target's own stored embedding. `embedding_v1` comes
    from an unpublished model with no callable endpoint, so arbitrary text cannot
    be projected into that space; patent-to-patent similarity is what the data
    actually supports.
    """
    client = bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)
    suffix = scope.lower()

    tables = dict(
        vectors=config.working_table(f"vectors_{suffix}"),
        dates=config.working_table(f"dates_{suffix}"),
        patents=config.working_table(f"patents_{suffix}_clustered"),
    )
    params = [
        bigquery.ScalarQueryParameter("target", "STRING", target),
        bigquery.ScalarQueryParameter("topn", "INT64", top_n),
    ]
    job_config = bigquery.QueryJobConfig(query_parameters=params)

    counts_job = client.query(FUNNEL_COUNTS_SQL.format(**tables), job_config=job_config)
    counts = list(counts_job.result())
    if not counts or counts[0]["corpus_size"] == 0:
        raise LookupError(
            f"no eligible prior art for {target}. Either the patent is not in the "
            f"{scope} corpus or it has no embedding."
        )
    c0 = counts[0]

    cand_job = client.query(CANDIDATES_SQL.format(**tables), job_config=job_config)
    rows = list(cand_job.result())

    billed = (counts_job.total_bytes_billed + cand_job.total_bytes_billed) / 1024**2
    print(f"  scan {billed:.0f} MB", file=sys.stderr)

    result = SearchResult(
        target=target,
        target_priority=str(c0["target_priority"]),
        corpus_size=c0["corpus_size"],
        dropped_not_prior_art=c0["dropped_not_prior_art"],
        dropped_same_family=c0["dropped_same_family"],
    )
    for r in rows:
        result.candidates.append(
            Candidate(
                patent_id=r["patent_id"],
                title=r["title"] or "",
                distance=r["distance"],
                filing_date=str(r["filing_date"]),
                priority_date=str(r["priority_date"]),
                grant_date=str(r["grant_date"]),
                disclosure=r["disclosure"] or "",
            )
        )
    return result


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Retrieve eligible prior art")
    ap.add_argument("target", help="patent id, for example 7240025")
    ap.add_argument("--top", type=int, default=2000)
    ap.add_argument("--scope", default="G06Q")
    args = ap.parse_args()

    res = retrieve(args.target, args.top, args.scope)
    print(f"target            {res.target}")
    print(f"corpus            {res.corpus_size:,}")
    print(f"not prior art     {res.dropped_not_prior_art:,} dropped")
    print(f"same family       {res.dropped_same_family:,} dropped")
    print(f"eligible          {res.eligible:,}")
    print(f"retrieved         {len(res.candidates):,}\n")
    for c in res.candidates[:10]:
        print(f"  {c.distance:.4f}  {c.patent_id}  {c.filing_date}  {c.title[:62]}")


if __name__ == "__main__":
    main()
