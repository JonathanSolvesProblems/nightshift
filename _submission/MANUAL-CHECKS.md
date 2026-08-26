# Checks you can run yourself

Everything here you do by hand. The automated suites are in TEST-PLAN.md; this is
the list for sitting down with a browser and a terminal.

Cost is noted where a step spends money. Anything unmarked is free.

**Setup, once per terminal session.** Pick the one that matches your shell.

Git Bash:

```bash
cd ~/OneDrive/Desktop/Projects/Time3/AllThingsAgentic
export GOOGLE_APPLICATION_CREDENTIALS="$PWD/.secrets/priorart-dev.json"
export PYTHONPATH="$PWD/src"
```

PowerShell:

```powershell
cd C:\Users\Jon_A\OneDrive\Desktop\Projects\Time3\AllThingsAgentic
$env:GOOGLE_APPLICATION_CREDENTIALS = "$PWD\.secrets\priorart-dev.json"
$env:PYTHONPATH = "$PWD\src"
```

Every command below uses forward slashes, which work in both.

---

## A. Click through the live site (5 minutes, free)

Use a **private/incognito window**. The point is to see what a judge sees.

| # | Link | You should see | Problem if |
|---|---|---|---|
| A1 | [Home](https://nightshift-1015687974010.us-central1.run.app) | Dark mineral page, "NIGHTSHIFT · PRIOR-ART CORE LOG", a patent input | Anything white and SaaS-looking, or a 500 |
| A2 | Home, type `abc`, submit | A page saying that is not a patent number | A stack trace or 500 |
| A3 | Home, type `4000000`, submit | "Cannot search against US 4000000", not in the G06Q corpus | A run starts anyway |
| A4 | [The demo run](https://nightshift-1015687974010.us-central1.run.app/run/10163121-c398c4bc) | Depth column with strata and seams; funnel counting 171,694 down to 39 | Empty column, or dashes in the counts |
| A5 | Same page, hover a green seam | Tooltip with patent number, depth, limitations | Nothing |
| A6 | Same page, click a reference in the Seams table | That reference's claim chart | 404 or 500 |
| A7 | [Accuracy](https://nightshift-1015687974010.us-central1.run.app/eval) | X 97.5%, Y 92.5%, control 18.8% | Any cell blank |
| A8 | Switch OS to light mode, reload the run page | Pale mineral stock, deep olive accent, all text readable | Anything washed out |
| A9 | Narrow the window to phone width | Nothing scrolls sideways, the form stacks | A horizontal scrollbar |

Read the tagline on A1 aloud. It says Nightshift **ranks** 171,695 and **reads**
2,000. Check that against the run page in A4, which says "read by Gemini 2,000".
Those two have to agree, and an earlier version of the tagline did not.

## B. The demo artifact (2 minutes, free)

[The claim chart](https://nightshift-1015687974010.us-central1.run.app/chart/10163121-c398c4bc?ref=7606730)

| # | Check |
|---|---|
| B1 | Header reads "PRIOR-ART EVIDENCE DOSSIER", US 7606730, 2002-06-25 |
| B2 | "Surfaced at depth 218 of 44,907 eligible references" |
| B3 | Row 1(pre) says TAUGHT BY THIS REFERENCE, with a verbatim quote about loyalty points at a merchant point of sale |
| B4 | At least one row says the reference does **not** teach a limitation |
| B5 | Footer: "Not a legal opinion and not a validity determination" |

B4 matters more than it looks. A chart with no gaps reads as generated. If every
row is green, something is wrong with the chart stage.

## C. Run the automated suites (3 minutes, free)

```powershell
python -m pytest tests/ -q                          # 15 passed
python scripts/test_failure_modes.py                # 12/12 passed
python scripts/audit_ui.py 10163121-c398c4bc        # 17/17 passed
python scripts/smoke_test.py                        # 171,703 G06Q patents
```

## D. Prove the numbers are real

The part worth doing personally: it is what a judge most wants to be true and
least is able to check.

| # | Command | Cost | Expect |
|---|---|---|---|
| D1 | `python -m priorart.corpus stats --scope G06Q` | free | 171,695 patents, 1976 to 2021 |
| D2 | `bq query --use_legacy_sql=false --project_id=prior-art-agent-2026 < scripts/gate_recall_compare.sql` | free | Old 64d vs new 768d: X @2k 54.0% then 83.9% |
| D3 | `python -m priorart.eval --n 12 --cats X` | ~$0.20 | X near 97%, control far below |
| D4 | `python -m priorart.eval --n 40 --cats X,Y` | ~$0.70 | Reproduces 97.5 / 92.5 / 18.8 exactly |
| D5 | `python scripts/test_gemini.py` | free | A limitation mapped to a verbatim span |

D2 is free and is the strongest single check: it shows the embedding upgrade
measured against the old one on the same pairs.

## E. Run the whole thing end to end

| # | Command | Cost | Time |
|---|---|---|---|
| E1 | `python -m priorart.run 10163121 --candidates 200` | ~$1 | ~2 min, local, no Cloud Run |
| E2 | `python -m priorart.orchestrate 10163121 --candidates 2000 --tasks 10` | ~$9 | ~4 min across 10 Cloud Run tasks |

E2 prints a run id. Open
`https://nightshift-1015687974010.us-central1.run.app/run/<run_id>` while it is
still going: tasks lighting up and the funnel counting down is the demo.

**Do not run E2 more than you need to.** It is the main cost in the project.

## F. The ADK agent

```powershell
python scripts/test_agent.py 10163121-c398c4bc
```

Four questions get asked. Watch the last one: asked whether the patent is
invalid, it must **refuse** and point at the claim chart. If it ever answers that
directly, that is the most important thing in this repo to fix.

## G. Watch it run on Google Cloud (this is your video footage)

| # | Link | What |
|---|---|---|
| G1 | [Cloud Run Jobs](https://console.cloud.google.com/run/jobs?project=prior-art-agent-2026) | `nightshift-worker` and its executions, 10 tasks each |
| G2 | [Job executions](https://console.cloud.google.com/run/jobs/details/us-central1/nightshift-worker/executions?project=prior-art-agent-2026) | Open one while E2 runs: tasks Running then Succeeded |
| G3 | [Logs](https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_run_job%22?project=prior-art-agent-2026) | Live worker output during a run |
| G4 | [BigQuery](https://console.cloud.google.com/bigquery?project=prior-art-agent-2026) | Dataset `corpus`, the tables and row counts |
| G5 | [Firestore](https://console.cloud.google.com/firestore/databases?project=prior-art-agent-2026) | Database `nightshift`, collection `runs` |
| G6 | [Cloud Run service](https://console.cloud.google.com/run/detail/us-central1/nightshift/metrics?project=prior-art-agent-2026) | The deployed service and its revisions |

G1 to G3 are the "backend running on Google Cloud" proof the rules require.

## H. Before you submit, logged out

| # | Link | Check |
|---|---|---|
| H1 | [Repo](https://github.com/JonathanSolvesProblems/nightshift) | Loads in a private window |
| H2 | Same | README renders, tables not broken |
| H3 | [Live URL](https://nightshift-1015687974010.us-central1.run.app) | Loads with no sign-in |
| H4 | Your video URL | Plays with no sign-in |
| H5 | Your Devpost project page | Loads in a private window |
| H6 | Same | Read the tagline **aloud** as a stranger. No drafting prose, no options, no brackets |
| H7 | [Gallery](https://allthingsagentichackathon.devpost.com/project-gallery) | **Search "Nightshift" and confirm it appears** |
| H8 | Devpost | Screenshot the submission confirmation |

H7 is not optional. A previous entry showed SUBMITTED in the portfolio, returned
HTTP 200 on its own page, and still returned zero results in the hackathon's own
gallery search. Nobody found out for two months.

## I. Sanity checks on the story

Read these aloud and see whether you believe them.

- The tagline in `_submission/submission.md`. Does it say what a person gets?
- The first 20 seconds of `_submission/demo-script.md`. Is there a human in it?
- ACCURACY.md "Scope, stated in full". Would a patent attorney catch anything hidden?
- Does anything anywhere claim a number the repo cannot regenerate?

## J. Also worth doing once

| # | Link | Why |
|---|---|---|
| J1 | [Hackathon rules](https://allthingsagentichackathon.devpost.com/details/rules) | Re-read the required components the week you submit |
| J2 | [Billing](https://console.cloud.google.com/billing?project=prior-art-agent-2026) | Confirm the $150 credit is applied and check spend |
| J3 | [Credits page](https://g.dev/cloud/all-things-agentic) | Confirm the grant landed on this project |

## If you only do four

**A1** and **A4** (it works and looks like itself), **B4** (the chart is honest
about what it did not find), **D2** (the numbers are real and it costs nothing),
and **H7** (a judge can actually find the entry).
