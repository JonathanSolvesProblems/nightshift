# Teardown

**Run `python scripts/teardown.py --destroy` on or after 12 October 2026.**

That date is the whole point of this file. The hackathon publishes a submission
deadline (31 August 2026, 17:00 PDT) and no judging end date, and "after judging
closes" is a condition rather than a plan. A previous project of mine left a
cloud instance running for 40 days past its judging window on exactly that
wording. Six weeks past the deadline clears any plausible announcement; if
winners are announced sooner, run it sooner.

Put the date in a calendar, not in a file. A file does not remind anyone.

## Standing cost while it waits

Low enough that the date can slip without much harm, which is deliberate: it was
designed this way rather than discovered to be so.

| | |
|---|---|
| BigQuery storage, 9.56 GB | ~$0.19/month |
| Artifact Registry, ~1.4 GB of images | ~$0.14/month |
| Cloud Run service | $0 idle, scales to zero, no min instances |
| Cloud Run job | $0 unless executed |
| Firestore | $0 at this document count |
| New searches | Off. Token-gated and capped at one per day |

About **$0.33/month**. The expensive thing, a run at ~$34, cannot be triggered by
a visitor.

## Before destroying: keep the work reachable at zero cost

The finished runs and claim charts are rendered from BigQuery and Firestore, so
they die with the backend. The video, the public repo, ACCURACY.md and the
committed screenshots in `docs/shots/` survive on their own and carry the
project. Before running `--destroy`:

1. Save the pages worth keeping as static HTML or PNG: the demo run, both claim
   charts, the accuracy page. `scripts/shoot.py` already does this.
2. Confirm the demo video is public and is linked from the README, since it
   becomes the primary artifact once the URL is gone.

## The sequence

```bash
python scripts/teardown.py            # inventory, changes nothing
python scripts/teardown.py --destroy  # asks for the project id, then releases
```

`--destroy` handles the Cloud Run service, the Cloud Run job and the BigQuery
dataset. The rest is deliberately manual because it is one-way:

- **Revoke the service-account key.** `.secrets/priorart-dev.json` sat on an
  internet-facing deployment; revoke it regardless of whether it was abused.
  [Service accounts console](https://console.cloud.google.com/iam-admin/serviceaccounts?project=prior-art-agent-2026)
- **Delete the Firestore database** `nightshift`.
  [Firestore console](https://console.cloud.google.com/firestore/databases?project=prior-art-agent-2026)
- **Delete the Artifact Registry repositories** `gcr.io` and
  `cloud-run-source-deploy`. Deleting a Cloud Run service does not take its
  images with it.
  [Artifact Registry](https://console.cloud.google.com/artifacts?project=prior-art-agent-2026)
- **Discard the run token** in `.secrets/run-token.txt`.

## Verify from outside, not from the console

A console status label is not evidence. After destroying:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://nightshift-1015687974010.us-central1.run.app
```

Expect a connection failure or 404, not 200. Then re-run
`python scripts/teardown.py` and confirm the inventory is empty.

No custom DNS was ever pointed at this service, so there is no A record to clean
up and no risk of a subdomain outliving the IP.
