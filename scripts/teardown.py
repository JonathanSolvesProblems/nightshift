"""Inventory everything this project bills for, and optionally release it.

Written during the build, on purpose. A teardown script authored months later,
when the SDK is stale and the service-account key has been rotated away, is a
teardown that does not get run. This one works today, which is the only time it
can be verified.

    python scripts/teardown.py              # inventory only, changes nothing
    python scripts/teardown.py --destroy    # release it, with confirmation

Run the inventory whenever you want to know what is costing money. Run
--destroy on the date written in TEARDOWN.md, not on the feeling that the
project is finished: the submission being filed and the judging being over are
different days, and the gap is where the waste lives.

What this deliberately does NOT do: revoke the service-account key or the run
token. Those are one-way and a provider shows a secret once, so they are listed
as manual steps in TEARDOWN.md with the console link, to be done last.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

from priorart import config  # noqa: E402

REGION = "us-central1"
SERVICE = "nightshift"
JOB = "nightshift-worker"


def exe(name: str) -> str:
    """Resolve a CLI by name.

    On Windows both gcloud and bq are .cmd shims, which subprocess will not find
    from the bare name. Getting this wrong fails silently as an empty inventory,
    which is the worst possible failure for a script whose entire job is to tell
    you what you are still paying for.
    """
    import shutil

    return shutil.which(name) or shutil.which(f"{name}.cmd") or name


def sh(cmd: list[str]) -> str:
    cmd = [exe(cmd[0]), *cmd[1:]]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0 and not r.stdout.strip():
            return f"(command failed: {(r.stderr or '').strip().splitlines()[-1:] or ''})"
        return r.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"(could not read: {type(exc).__name__})"


def inventory() -> dict[str, list[str]]:
    """Everything with a recurring or potential cost, by service."""
    p = config.PROJECT_ID
    found: dict[str, list[str]] = {}

    found["Cloud Run services"] = [
        line for line in sh([
            "gcloud", "run", "services", "list", "--project", p,
            "--format=value(metadata.name,region,"
            "spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])",
        ]).splitlines() if line
    ]
    found["Cloud Run jobs"] = [
        line for line in sh([
            "gcloud", "run", "jobs", "list", "--project", p,
            "--format=value(metadata.name,region)",
        ]).splitlines() if line
    ]
    found["Artifact Registry repos"] = [
        line for line in sh([
            "gcloud", "artifacts", "repositories", "list", "--project", p,
            "--format=value(name,format,sizeBytes)",
        ]).splitlines() if line
    ]

    # BigQuery: the only meaningful standing storage cost.
    try:
        from google.cloud import bigquery

        c = bigquery.Client(project=p, location=config.LOCATION)
        rows = []
        total = 0
        for t in c.list_tables(config.DATASET):
            tb = c.get_table(t)
            total += tb.num_bytes
            rows.append(f"{tb.table_id}  {tb.num_bytes / 1024**3:.2f} GB")
        rows.append(f"-- total {total / 1024**3:.2f} GB, "
                    f"about ${total / 1024**3 * 0.02:.2f}/month")
        found[f"BigQuery tables in {config.DATASET}"] = rows
    except Exception as exc:  # noqa: BLE001
        found["BigQuery"] = [f"(could not read: {exc})"]

    # Firestore documents are free at this volume but listed for completeness,
    # because "we deleted the compute" is not the same as "we deleted the data".
    try:
        from priorart import store

        runs = store.recent_runs(50)
        found["Firestore runs"] = [
            f"{r.get('run_id')}  {r.get('status')}" for r in runs
        ] or ["(none)"]
    except Exception as exc:  # noqa: BLE001
        found["Firestore"] = [f"(could not read: {exc})"]

    return found


def destroy() -> None:
    p = config.PROJECT_ID
    print(f"\nThis releases billable resources in {p}.")
    print("The public URL, every finished run and every claim chart go with it.")
    if input("Type the project id to confirm: ").strip() != p:
        print("Not confirmed. Nothing changed.")
        return

    steps = [
        ([exe("gcloud"), "run", "services", "delete", SERVICE, "--region", REGION,
          "--project", p, "--quiet"], "Cloud Run service"),
        ([exe("gcloud"), "run", "jobs", "delete", JOB, "--region", REGION,
          "--project", p, "--quiet"], "Cloud Run job"),
        ([exe("bq"), "rm", "-r", "-f", "-d", f"{p}:{config.DATASET}"], "BigQuery dataset"),
    ]
    for cmd, what in steps:
        print(f"  releasing {what} ...", flush=True)
        subprocess.run(cmd, check=False)

    print("\nDone. Still manual, and deliberately so, see TEARDOWN.md:")
    print("  - revoke the service-account key")
    print("  - delete the Firestore database")
    print("  - delete Artifact Registry images")
    print("  - verify from OUTSIDE that the URL is gone, not from the console label")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--destroy", action="store_true",
                    help="actually release resources (asks for confirmation)")
    args = ap.parse_args()

    print(f"project {config.PROJECT_ID}\n")
    for service, items in inventory().items():
        print(f"{service}:")
        for i in items:
            print(f"  {i}")
        print()

    if args.destroy:
        destroy()
    else:
        print("Inventory only. Nothing was changed. Pass --destroy to release.")


if __name__ == "__main__":
    main()
