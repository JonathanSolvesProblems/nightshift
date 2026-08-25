"""Prepare a run and launch the Cloud Run Job that executes it.

The expensive, corpus-wide work happens exactly once here: decompose the claim,
apply the priority-date gate, rank the eligible corpus, and materialize the
result into a per-run BigQuery table. Workers then read slices of that table.

Separating this from the workers is what makes the fan-out affordable. Retrieval
scans about 1.3 GB; doing it inside each of N tasks would multiply that by N and
buy nothing.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid

from google.cloud import bigquery, run_v2

from . import config, corpus, judge, search, store

REGION = os.environ.get("PRIOR_ART_REGION", "us-central1")
JOB_NAME = os.environ.get("PRIOR_ART_JOB", "nightshift-worker")


RANKED_SQL = search.TARGET_CTE + """
SELECT
  c.patent_id,
  p.title,
  p.grant_date,
  p.disclosure,
  d.filing_date,
  d.priority_date,
  ML.DISTANCE(t.tvec, c.embedding_v1, 'COSINE') AS distance,
  ROW_NUMBER() OVER (
    ORDER BY ML.DISTANCE(t.tvec, c.embedding_v1, 'COSINE')
  ) - 1 AS rank
FROM t, `{vectors}` c
JOIN `{dates}` d ON d.patent_id = c.patent_id
JOIN `{patents}` p ON p.patent_id = c.patent_id
WHERE c.patent_id != @target
  AND d.filing_date < t.t_priority
  AND NOT (p.title = t.t_title OR d.priority_date = t.t_priority)
QUALIFY rank < @topn
"""


def prepare(target_id: str, n_candidates: int, scope: str = "G06Q") -> str:
    """Build the run's candidate table and Firestore record. Returns run_id."""
    run_id = f"{target_id}-{uuid.uuid4().hex[:8]}"
    suffix = scope.lower()

    target = corpus.get_target(target_id, scope)
    gc = judge.client()
    limitations = judge.split_claim(target.claim_1, gc)
    print(f"claim 1 -> {len(limitations)} limitations", file=sys.stderr)

    client = bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)
    tables = dict(
        vectors=config.working_table(f"vectors_{suffix}"),
        dates=config.working_table(f"dates_{suffix}"),
        patents=config.working_table(f"patents_{suffix}_clustered"),
    )
    params = [
        bigquery.ScalarQueryParameter("target", "STRING", target_id),
        bigquery.ScalarQueryParameter("topn", "INT64", n_candidates),
    ]

    dest = config.working_table(f"run_{run_id}")
    job = client.query(
        RANKED_SQL.format(**tables),
        job_config=bigquery.QueryJobConfig(
            query_parameters=params,
            destination=dest,
            write_disposition="WRITE_TRUNCATE",
            clustering_fields=["patent_id"],
        ),
    )
    job.result()
    print(f"candidates -> {dest} ({job.total_bytes_billed / 1024**2:.0f} MB)",
          file=sys.stderr)

    # Funnel counts for the UI, computed without touching the disclosure column.
    counts_job = client.query(
        search.FUNNEL_COUNTS_SQL.format(**tables),
        job_config=bigquery.QueryJobConfig(query_parameters=params),
    )
    c0 = list(counts_job.result())[0]

    store.create_run(
        run_id,
        target_id,
        {
            "title": target.title,
            "grant_date": target.grant_date,
            "priority_date": str(c0["target_priority"]),
            "n_claims": len(target.claims),
            "limitations": [{"index": l.index, "text": l.text} for l in limitations],
            "corpus_size": c0["corpus_size"],
            "dropped_not_prior_art": c0["dropped_not_prior_art"],
            "dropped_same_family": c0["dropped_same_family"],
            "eligible": c0["corpus_size"]
            - c0["dropped_not_prior_art"]
            - c0["dropped_same_family"],
            "candidates": n_candidates,
            "model": judge.MODEL,
        },
    )
    return run_id


def launch(run_id: str, tasks: int) -> str:
    """Execute the Cloud Run Job with this run's id and task count."""
    client = run_v2.JobsClient()
    name = f"projects/{config.PROJECT_ID}/locations/{REGION}/jobs/{JOB_NAME}"

    overrides = run_v2.RunJobRequest.Overrides(
        task_count=tasks,
        container_overrides=[
            run_v2.RunJobRequest.Overrides.ContainerOverride(
                env=[run_v2.EnvVar(name="RUN_ID", value=run_id)]
            )
        ],
    )
    op = client.run_job(request=run_v2.RunJobRequest(name=name, overrides=overrides))
    execution = op.metadata.name if op.metadata else "(pending)"
    store.update_run(run_id, status="launched", execution=execution, tasks=tasks,
                     launched_at=time.time())
    return execution


def main() -> None:
    ap = argparse.ArgumentParser(description="Launch a Nightshift run")
    ap.add_argument("target")
    ap.add_argument("--candidates", type=int, default=2000)
    ap.add_argument("--tasks", type=int, default=10)
    ap.add_argument("--scope", default="G06Q")
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()

    run_id = prepare(args.target, args.candidates, args.scope)
    print(f"run_id {run_id}", file=sys.stderr)

    if args.prepare_only:
        return

    execution = launch(run_id, args.tasks)
    print(f"execution {execution}", file=sys.stderr)
    print(run_id)


if __name__ == "__main__":
    main()
