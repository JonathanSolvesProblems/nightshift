"""Build and read the working prior-art corpus on BigQuery.

Design note, derived from measurement rather than assumption.

Querying the public tables per request is not survivable on the free tier:

  one description lookup on patents.publications   1052.42 GB
  one claims lookup on patents.publications         116.67 GB
  one target fetch joining patentsview.claim         40.16 GB

None of those tables are partitioned or clustered on patent id, so a WHERE
filter still scans the whole column. So the corpus is materialized once into my
own dataset, and everything downstream, including the target patent fetch,
reads that small local table.

Every query is priced by dry run before it is allowed to execute. Cost
discipline is part of the design because the whole project runs inside a 1 TB
monthly allowance.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from google.cloud import bigquery

from . import config


@dataclass
class Target:
    """The patent someone is being sued over."""

    patent_id: str
    title: str
    abstract: str
    grant_date: str
    subgroups: list[str]
    claims: list[str]

    @property
    def claim_1(self) -> str:
        return self.claims[0] if self.claims else ""


class ScanTooLarge(RuntimeError):
    """Raised when a query would scan more than the configured ceiling."""


def client() -> bigquery.Client:
    return bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)


def price(bq: bigquery.Client, sql: str, params: list | None = None) -> float:
    """Return the GB a query would scan, without running it."""
    job_config = bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False, query_parameters=params or []
    )
    return bq.query(sql, job_config=job_config).total_bytes_processed / 1024**3


def run(
    bq: bigquery.Client,
    sql: str,
    params: list | None = None,
    ceiling_gb: float | None = None,
    destination: str | None = None,
):
    """Price a query, refuse it if it is too big, then run it."""
    ceiling = config.DEFAULT_SCAN_CEILING_GB if ceiling_gb is None else ceiling_gb
    gb = price(bq, sql, params)
    if gb > ceiling:
        raise ScanTooLarge(
            f"query would scan {gb:.2f} GB, ceiling is {ceiling:.2f} GB. "
            "Raise PRIOR_ART_SCAN_CEILING_GB only if you mean to spend it."
        )
    print(f"  scan {gb:.2f} GB", file=sys.stderr)

    job_config = bigquery.QueryJobConfig(query_parameters=params or [])
    if destination:
        job_config.destination = destination
        job_config.write_disposition = "WRITE_TRUNCATE"
    return bq.query(sql, job_config=job_config).result()


def scope_predicate(scope: str) -> str:
    """CPC scope can be a subsection (G06) or a group (G06Q)."""
    return "group_id = @scope" if len(scope) == 4 else "subsection_id = @scope"


# ---------------------------------------------------------------------------
# Bootstrap: the one expensive step
# ---------------------------------------------------------------------------


def bootstrap_sql(scope: str) -> str:
    return f"""
WITH in_scope AS (
  SELECT DISTINCT patent_id
  FROM `{config.SRC_CPC}`
  WHERE {scope_predicate(scope)}
),
subgroups AS (
  SELECT patent_id, ARRAY_AGG(DISTINCT subgroup_id IGNORE NULLS) AS subgroups
  FROM `{config.SRC_CPC}`
  WHERE patent_id IN (SELECT patent_id FROM in_scope)
  GROUP BY patent_id
),
claims AS (
  SELECT patent_id,
         ARRAY_AGG(text ORDER BY SAFE_CAST(sequence AS INT64)) AS claims
  FROM `{config.SRC_CLAIM}`
  WHERE patent_id IN (SELECT patent_id FROM in_scope)
  GROUP BY patent_id
)
SELECT
  p.id AS patent_id,
  p.title,
  p.abstract,
  p.date AS grant_date,
  p.num_claims,
  s.subgroups,
  IFNULL(c.claims, []) AS claims,
  SUBSTR(
    CONCAT(IFNULL(p.abstract, ''), chr(10),
           ARRAY_TO_STRING(IFNULL(c.claims, []), chr(10))),
    1, {config.MAX_DISCLOSURE_CHARS}
  ) AS disclosure
FROM `{config.SRC_PATENT}` AS p
JOIN subgroups AS s ON s.patent_id = p.id
LEFT JOIN claims AS c ON c.patent_id = p.id
WHERE p.country = 'US' AND IFNULL(p.withdrawn, 0) = 0
"""


def embeddings_sql(corpus_table: str) -> str:
    """Pull precomputed patent embeddings for the corpus.

    google_patents_research.vector_db is keyed by publication number
    (US-7650331-B1) while patentsview is keyed by bare id (7650331), so the id
    is split out rather than joined on a LIKE.
    """
    return f"""
SELECT
  SPLIT(publication_number, '-')[SAFE_OFFSET(1)] AS patent_id,
  embedding_v1
FROM `{config.SRC_VECTORS}`
WHERE publication_number LIKE 'US-%'
  AND SPLIT(publication_number, '-')[SAFE_OFFSET(1)]
      IN (SELECT patent_id FROM `{corpus_table}`)
"""


def bootstrap(scope: str, execute: bool = False) -> None:
    """Materialize one CPC scope into my own dataset. Runs once."""
    bq = client()
    params = [bigquery.ScalarQueryParameter("scope", "STRING", scope)]
    corpus_table = config.working_table(f"patents_{scope.lower()}")
    vec_table = config.working_table(f"vectors_{scope.lower()}")

    corpus_gb = price(bq, bootstrap_sql(scope), params)
    print(f"corpus  {scope}: {corpus_gb:.2f} GB", file=sys.stderr)

    if not execute:
        print("dry run, nothing executed", file=sys.stderr)
        return

    bq.create_dataset(
        bigquery.Dataset(f"{config.PROJECT_ID}.{config.DATASET}"), exists_ok=True
    )
    run(bq, bootstrap_sql(scope), params, destination=corpus_table)
    print(f"wrote {corpus_table}", file=sys.stderr)

    run(bq, embeddings_sql(corpus_table), destination=vec_table)
    print(f"wrote {vec_table}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Reads, all against the local corpus
# ---------------------------------------------------------------------------


def get_target(patent_id: str, scope: str) -> Target:
    """Fetch the asserted patent from the materialized corpus."""
    bq = client()
    sql = f"""
    SELECT patent_id, title, abstract, grant_date, subgroups, claims
    FROM `{config.working_table(f"patents_{scope.lower()}")}`
    WHERE patent_id = @patent_id
    """
    params = [bigquery.ScalarQueryParameter("patent_id", "STRING", patent_id)]
    rows = list(run(bq, sql, params))
    if not rows:
        raise LookupError(f"patent {patent_id} not in corpus for scope {scope}")
    r = rows[0]
    return Target(
        patent_id=r["patent_id"],
        title=r["title"] or "",
        abstract=r["abstract"] or "",
        grant_date=str(r["grant_date"]),
        subgroups=list(r["subgroups"] or []),
        claims=list(r["claims"] or []),
    )


def corpus_stats(scope: str) -> dict:
    """Honest denominator for the depth claim."""
    bq = client()
    table = config.working_table(f"patents_{scope.lower()}")
    sql = f"""
    SELECT COUNT(*) AS patents,
           MIN(grant_date) AS earliest,
           MAX(grant_date) AS latest,
           COUNTIF(ARRAY_LENGTH(claims) > 0) AS with_claims
    FROM `{table}`
    """
    r = list(run(bq, sql))[0]
    return dict(r)


def main() -> None:
    ap = argparse.ArgumentParser(description="Prior-art corpus tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bootstrap", help="materialize a CPC scope")
    b.add_argument("--scope", required=True, help="G06Q (group) or G06 (subsection)")
    b.add_argument("--execute", action="store_true", help="actually run it")

    t = sub.add_parser("target", help="fetch one patent from the corpus")
    t.add_argument("patent_id")
    t.add_argument("--scope", default="G06Q")

    s = sub.add_parser("stats", help="corpus size")
    s.add_argument("--scope", default="G06Q")

    args = ap.parse_args()
    if args.cmd == "bootstrap":
        bootstrap(args.scope, execute=args.execute)
    elif args.cmd == "target":
        target = get_target(args.patent_id, args.scope)
        print(f"{target.patent_id}  {target.title}")
        print(f"granted {target.grant_date}")
        print(f"cpc {', '.join(target.subgroups[:8])}")
        print(f"{len(target.claims)} claims\n")
        print(target.claim_1[:1500])
    elif args.cmd == "stats":
        for k, v in corpus_stats(args.scope).items():
            print(f"{k:14} {v}")


if __name__ == "__main__":
    main()
