"""Measure real bytes billed for a target lookup, clustered vs not.

Dry runs report an upper bound and do not model cluster pruning, so the only
honest way to check whether clustering helped is to run the query and read the
job statistics back.
"""

from google.cloud import bigquery

PROJECT = "prior-art-agent-2026"
TABLES = {
    "unclustered": "prior-art-agent-2026.corpus.patents_g06q",
    "clustered": "prior-art-agent-2026.corpus.patents_g06q_clustered",
}
PATENT = "7240025"


def main() -> None:
    client = bigquery.Client(project=PROJECT)
    for label, table in TABLES.items():
        sql = (
            f"SELECT patent_id, title, ARRAY_LENGTH(claims) AS n "
            f"FROM `{table}` WHERE patent_id = @pid"
        )
        job = client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("pid", "STRING", PATENT)
                ]
            ),
        )
        rows = list(job.result())
        mb = job.total_bytes_processed / 1024**2
        billed = job.total_bytes_billed / 1024**2
        print(
            f"{label:13} processed {mb:8.1f} MB   billed {billed:8.1f} MB   "
            f"rows {len(rows)}"
        )


if __name__ == "__main__":
    main()
