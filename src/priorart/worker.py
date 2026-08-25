"""Cloud Run Job task: screen one shard of a run's candidate set.

Cloud Run Jobs give every task `CLOUD_RUN_TASK_INDEX` and `CLOUD_RUN_TASK_COUNT`
and nothing else. Tasks never talk to each other, so the shard boundary has to be
derivable from the index alone.

The orchestrator materializes the ranked candidate set once into a per-run
BigQuery table. Each task then reads only its own slice with
`MOD(rank, task_count) = task_index`. Running retrieval inside every task instead
would rescan the corpus once per worker, which is the obvious design and the
wrong one: it multiplies a 1.3 GB scan by the worker count for no benefit.

Findings are written to Firestore the moment they are found, so a task that dies
does not take its results with it and the browser sees progress throughout.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import asdict, dataclass

from google.cloud import bigquery

from . import config, judge, store


@dataclass
class ShardCandidate:
    patent_id: str
    title: str
    filing_date: str
    disclosure: str
    rank: int = 0


SHARD_SQL = """
SELECT patent_id, title, filing_date, disclosure, rank
FROM `{table}`
WHERE MOD(rank, @task_count) = @task_index
ORDER BY rank
"""


def load_shard(run_id: str, index: int, count: int) -> list[ShardCandidate]:
    client = bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)
    sql = SHARD_SQL.format(table=config.working_table(f"run_{run_id}"))
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("task_count", "INT64", count),
                bigquery.ScalarQueryParameter("task_index", "INT64", index),
            ]
        ),
    )
    return [
        ShardCandidate(
            patent_id=r["patent_id"],
            title=r["title"] or "",
            filing_date=str(r["filing_date"]),
            disclosure=r["disclosure"] or "",
            rank=int(r["rank"]),
        )
        for r in job.result()
    ]


def main() -> int:
    run_id = os.environ["RUN_ID"]
    index = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    count = int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1"))
    workers = int(os.environ.get("PRIOR_ART_WORKERS", "12"))

    run = store.get_run(run_id)
    if not run:
        print(f"run {run_id} not found", file=sys.stderr)
        return 1

    limitations = [
        judge.Limitation(index=l["index"], text=l["text"])
        for l in run.get("limitations", [])
    ]
    if not limitations:
        print("run has no limitations recorded", file=sys.stderr)
        return 1

    candidates = load_shard(run_id, index, count)
    store.start_shard(run_id, index, count, len(candidates))
    print(f"shard {index}/{count}: {len(candidates)} candidates", file=sys.stderr)

    if index == 0:
        store.update_run(run_id, status="running", started_at=time.time())

    screened = 0
    findings = 0
    tokens_in = 0
    tokens_out = 0
    started = time.time()

    # Depth position in the UI encodes rank, so the rank has to travel with the
    # verdict. The screening call itself never sees it: a candidate's position in
    # the ranking must not influence the judgment of what it discloses.
    rank_by_id = {c.patent_id: c.rank for c in candidates}
    date_by_id = {c.patent_id: c.filing_date for c in candidates}

    def on_result(v: judge.Verdict) -> None:
        nonlocal screened, findings, tokens_in, tokens_out
        screened += 1
        tokens_in += v.tokens_in
        tokens_out += v.tokens_out
        if v.relevant:
            findings += 1
            record = asdict(v)
            record["rank"] = rank_by_id.get(v.patent_id, 0)
            record["filing_date"] = date_by_id.get(v.patent_id, v.filing_date)
            store.add_finding(run_id, record)
        # Firestore writes are not free, so progress is flushed in batches while
        # findings are written immediately.
        if screened % 25 == 0 or screened == len(candidates):
            store.bump_shard(run_id, index, screened, findings)

    judge.screen_all(
        candidates, limitations, blind=True, workers=workers, on_result=on_result
    )

    elapsed = time.time() - started
    cost = tokens_in / 1e6 * 1.50 + tokens_out / 1e6 * 9.00
    store.finish_shard(
        run_id,
        index,
        screened=screened,
        findings=findings,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        usd=round(cost, 4),
        seconds=round(elapsed, 1),
    )

    print(
        f"shard {index} done: {screened} screened, {findings} findings, "
        f"{elapsed:.0f}s, ${cost:.4f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
