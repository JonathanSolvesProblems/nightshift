"""Smoke test: prove BigQuery access works from Python with real data.

Run:
    set GOOGLE_APPLICATION_CREDENTIALS=.secrets\\priorart-dev.json
    python scripts\\smoke_test.py
"""

import sys

from google.cloud import bigquery

PROJECT = "prior-art-agent-2026"

CHECKS = {
    "G06Q patents in scope": """
        SELECT COUNT(DISTINCT patent_id) AS n
        FROM `patents-public-data.patentsview.cpc_current`
        WHERE group_id = 'G06Q'
    """,
    "embeddings available": """
        SELECT COUNT(*) AS n
        FROM `patents-public-data.google_patents_research.vector_db`
        WHERE publication_number BETWEEN 'US-7650331-A' AND 'US-7650331-Z'
    """,
}


def main() -> int:
    client = bigquery.Client(project=PROJECT)
    print(f"project {PROJECT}")

    for label, sql in CHECKS.items():
        dry = client.query(
            sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        )
        gb = dry.total_bytes_processed / 1024**3
        rows = list(client.query(sql).result())
        print(f"  {label:26} {rows[0]['n']:>10,}   (scanned {gb:.2f} GB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
