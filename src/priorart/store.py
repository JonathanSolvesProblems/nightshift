"""Run state in Firestore.

A run is a long background job. It is started by one request, executed by many
Cloud Run Job tasks that never talk to each other, and watched by a browser that
may connect long after the work began. Firestore is the shared surface all three
meet on.

Layout:

    runs/{run_id}                     status, funnel counts, cost, timings
    runs/{run_id}/findings/{ref_id}   one document per relevant reference
    runs/{run_id}/shards/{index}      per-task progress, so a stalled worker shows

Findings are written as they are found rather than at the end, because a job
that takes 40 minutes must show progress the whole way, and because a worker
that dies should not take its results with it.
"""

from __future__ import annotations

import os
import time
from dataclasses import asdict, is_dataclass

from google.cloud import firestore

from . import config

_client: firestore.Client | None = None


def db() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client(
            project=os.environ.get("PRIOR_ART_PROJECT", config.PROJECT_ID)
        )
    return _client


def run_ref(run_id: str):
    return db().collection("runs").document(run_id)


def create_run(run_id: str, target: str, meta: dict) -> None:
    run_ref(run_id).set(
        {
            "run_id": run_id,
            "target": target,
            "status": "queued",
            "created_at": time.time(),
            "findings": 0,
            "screened": 0,
            **meta,
        }
    )


def update_run(run_id: str, **fields) -> None:
    run_ref(run_id).set(fields, merge=True)


def get_run(run_id: str) -> dict | None:
    snap = run_ref(run_id).get()
    return snap.to_dict() if snap.exists else None


def start_shard(run_id: str, index: int, total: int, count: int) -> None:
    run_ref(run_id).collection("shards").document(str(index)).set(
        {
            "index": index,
            "of": total,
            "assigned": count,
            "screened": 0,
            "findings": 0,
            "status": "running",
            "started_at": time.time(),
        }
    )


def bump_shard(run_id: str, index: int, screened: int, findings: int) -> None:
    doc = run_ref(run_id).collection("shards").document(str(index))
    doc.set(
        {
            "screened": screened,
            "findings": findings,
            "updated_at": time.time(),
        },
        merge=True,
    )


def finish_shard(run_id: str, index: int, **fields) -> None:
    run_ref(run_id).collection("shards").document(str(index)).set(
        {"status": "done", "finished_at": time.time(), **fields}, merge=True
    )


def add_finding(run_id: str, verdict) -> None:
    """Write one relevant reference the moment it is found."""
    data = asdict(verdict) if is_dataclass(verdict) else dict(verdict)
    data["found_at"] = time.time()
    run_ref(run_id).collection("findings").document(str(data["patent_id"])).set(data)


def list_findings(run_id: str, limit: int = 100) -> list[dict]:
    """Findings are sorted in Python rather than by Firestore.

    Ordering in the query would need an index on a subcollection field, and an
    index that is still building returns an error rather than a slower result.
    A run has at most a few hundred findings, so sorting here costs nothing and
    removes a deployment-time dependency.
    """
    try:
        docs = run_ref(run_id).collection("findings").limit(limit).stream()
        rows = [d.to_dict() for d in docs]
    except Exception:  # noqa: BLE001 - a read failure must not blank the page
        return []
    return sorted(rows, key=lambda f: (f.get("relevance", 0), f.get("found_at", 0)),
                  reverse=True)


def list_shards(run_id: str) -> list[dict]:
    try:
        docs = run_ref(run_id).collection("shards").stream()
    except Exception:  # noqa: BLE001
        return []
    return sorted((d.to_dict() for d in docs), key=lambda s: s.get("index", 0))


def recent_runs(limit: int = 20) -> list[dict]:
    """Recent runs, newest first.

    Read defensively and sorted in Python. This list is a convenience on the
    landing page, and a slow or failing Firestore read must not turn the entry
    point of the whole service into a 500.
    """
    try:
        docs = db().collection("runs").limit(limit * 3).stream()
        rows = [d.to_dict() for d in docs]
    except Exception:  # noqa: BLE001
        return []
    rows.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    return rows[:limit]
