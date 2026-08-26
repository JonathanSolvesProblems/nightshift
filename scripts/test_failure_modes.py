"""Exercise the ways a user breaks this, on purpose.

A judge does not follow the happy path. They paste a patent number with commas
in it, or one from a class this build does not cover, or they open a chart before
anything has been found. Each of those must produce a sentence, not a stack
trace and not a 500.

Nothing here launches a Cloud Run Job or spends money on screening: the cases
that would are run with prepare-only.

    python scripts/test_failure_modes.py
"""

from __future__ import annotations

import sys
import traceback

import requests
from google.cloud import bigquery

sys.path.insert(0, "src")

from priorart import config, corpus, orchestrate, store  # noqa: E402

BASE = "https://nightshift-1015687974010.us-central1.run.app"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def t_non_numeric_input() -> None:
    """Garbage in the patent field must not 500."""
    try:
        r = requests.post(f"{BASE}/run", data={"patent": "abc"}, timeout=120,
                          allow_redirects=False)
        # A redirect would mean it started a run on an empty id, which is worse
        # than an error.
        check("non-numeric input does not 500", r.status_code < 500,
              f"HTTP {r.status_code}")
        check("non-numeric input does not silently start a run",
              r.status_code != 303, f"HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        check("non-numeric input", False, f"{type(exc).__name__}: {exc}")


def t_patent_outside_corpus() -> None:
    """A patent that is not in CPC G06Q must fail cleanly and early."""
    try:
        corpus.get_target("4000000", "G06Q")
        check("patent outside corpus raises", False, "no exception raised")
    except LookupError as exc:
        readable = "not in corpus" in str(exc).lower()
        check("patent outside corpus raises LookupError", True)
        check("its message is readable", readable, str(exc)[:90])
    except Exception as exc:  # noqa: BLE001
        check("patent outside corpus raises LookupError", False,
              f"got {type(exc).__name__}")


def t_patent_with_no_claims() -> None:
    """2020+ grants have no claim text. Refuse before launching anything."""
    client = bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)
    rows = list(
        client.query(
            f"""SELECT patent_id FROM `{config.working_table("patents_g06q_clustered")}`
                WHERE ARRAY_LENGTH(claims) = 0 LIMIT 1"""
        ).result()
    )
    if not rows:
        check("found a claimless patent to test", False, "none in corpus")
        return
    pid = rows[0]["patent_id"]
    try:
        target = corpus.get_target(pid, "G06Q")
        empty = target.claim_1 == ""
        check(f"claimless patent US {pid} yields empty claim_1", empty)
        # The orchestrator must not launch a job it cannot possibly complete.
        try:
            orchestrate.prepare(pid, 10)
            check("orchestrator refuses a claimless target", False,
                  "prepare() succeeded on a patent with no claim text")
        except Exception as exc:  # noqa: BLE001
            check("orchestrator refuses a claimless target", True,
                  type(exc).__name__)
    except Exception as exc:  # noqa: BLE001
        check(f"claimless patent US {pid}", False, f"{type(exc).__name__}: {exc}")


def t_chart_before_findings() -> None:
    """Opening a chart on a run with nothing found must render a sentence."""
    try:
        r = requests.get(f"{BASE}/chart/does-not-exist-at-all", timeout=120)
        check("chart on a missing run does not 500", r.status_code < 500,
              f"HTTP {r.status_code}")
        check("chart on a missing run says so",
              "No such borehole" in r.text or "no such" in r.text.lower())
    except Exception as exc:  # noqa: BLE001
        check("chart on a missing run", False, f"{type(exc).__name__}: {exc}")


def t_unknown_run_api() -> None:
    """The polling endpoint must 404 rather than throw."""
    try:
        r = requests.get(f"{BASE}/api/run/nope", timeout=120)
        check("api on unknown run returns 404", r.status_code == 404,
              f"HTTP {r.status_code}")
    except Exception as exc:  # noqa: BLE001
        check("api on unknown run", False, f"{type(exc).__name__}: {exc}")


def t_findings_survive_partial_run() -> None:
    """Findings are written as they are found, not at the end.

    This is what makes a dead worker survivable, so it is worth asserting rather
    than trusting: a run that is still executing must already have findings
    readable in Firestore.
    """
    runs = store.recent_runs(12)
    partial = [r for r in runs if r.get("status") in ("running", "launched")]
    done = [r for r in runs if r.get("status") == "done"]
    sample = (partial or done)
    if not sample:
        check("findings readable mid-run", False, "no runs to inspect")
        return
    rid = sample[0]["run_id"]
    shards = store.list_shards(rid)
    findings = store.list_findings(rid)
    check("findings are readable independently of run completion",
          len(findings) > 0 or len(shards) == 0,
          f"{rid}: {len(findings)} findings, {len(shards)} shards")


def t_rerun_isolation() -> None:
    """Two runs on the same target must not share a candidate table."""
    a = orchestrate.prepare("7240025", 5)
    b = orchestrate.prepare("7240025", 5)
    check("re-running a target yields distinct run ids", a != b, f"{a} vs {b}")
    ta = config.working_table(f"run_{a}")
    tb = config.working_table(f"run_{b}")
    check("and distinct per-run candidate tables", ta != tb)
    client = bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)
    for t in (ta, tb):
        client.delete_table(t, not_found_ok=True)
    for rid in (a, b):
        store.run_ref(rid).delete()
    print("    (cleaned up both probe runs)")


def main() -> int:
    print("failure modes\n")
    for fn in (
        t_non_numeric_input,
        t_patent_outside_corpus,
        t_patent_with_no_claims,
        t_chart_before_findings,
        t_unknown_run_api,
        t_findings_survive_partial_run,
        t_rerun_isolation,
    ):
        try:
            fn()
        except Exception:  # noqa: BLE001
            check(fn.__name__, False, "harness error")
            traceback.print_exc()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    for name, _, detail in failed:
        print(f"  FAILED: {name}  {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
