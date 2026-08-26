# Checks you can run yourself

Everything here is something you do by hand. The automated suites are in
TEST-PLAN.md; this is the list for sitting down with a browser and a terminal.

Cost is noted where a step spends money. Anything unmarked is free.

**Setup, once per terminal session:**

```powershell
cd C:\Users\Jon_A\OneDrive\Desktop\Projects\Time3\AllThingsAgentic
$env:GOOGLE_APPLICATION_CREDENTIALS = "$PWD\.secrets\priorart-dev.json"
$env:PYTHONPATH = "$PWD\src"
```

---

## A. Click through the live site (5 minutes, free)

Do this in a **private/incognito window**, because the point is to see what a
judge sees, not what your logged-in browser sees.

| # | Do this | You should see | Problem if |
|---|---|---|---|
| A1 | Open https://nightshift-1015687974010.us-central1.run.app | Dark mineral page, "NIGHTSHIFT · PRIOR-ART CORE LOG", a patent input | Anything white/SaaS-looking, or a 500 |
| A2 | Type `abc` and submit | A page saying that is not a patent number | A stack trace or 500 |
| A3 | Type `4000000` and submit | "Cannot search against US 4000000", explaining it is not in the G06Q corpus | A run starts anyway |
| A4 | Click the run `10163121-c398c4bc` in Recent boreholes | Depth column with strata and seams, funnel counting 171,694 down to 39 | Empty column, or counts showing dashes |
| A5 | Hover a seam in the depth column | Tooltip: patent number, depth, limitations | Nothing |
| A6 | Click a reference in the Seams table | Its claim chart | 404 or 500 |
| A7 | Open /eval | Three rows: X 97.5%, Y 92.5%, control 18.8% | Any cell blank |
| A8 | Switch your OS to light mode, reload | Pale mineral stock, deep olive accent, all text readable | Anything unreadable or washed out |
| A9 | Narrow the window to phone width | Nothing scrolls sideways, form stacks | Horizontal scrollbar |

## B. The demo artifact (2 minutes, free)

| # | Do this | You should see |
|---|---|---|
| B1 | Open /chart/10163121-c398c4bc?ref=7606730 | "PRIOR-ART EVIDENCE DOSSIER", US 7606730, 2002-06-25 |
| B2 | Read the header line | "Surfaced at depth 218 of 44,907 eligible references" |
| B3 | Read row 1(pre) | "TAUGHT BY THIS REFERENCE" and a verbatim quote about loyalty points at a merchant point of sale |
| B4 | Scroll to the bottom | At least one row saying the reference does NOT teach a limitation |
| B5 | Read the footer | "Not a legal opinion and not a validity determination" |

B4 matters more than it looks. A chart with no gaps in it reads as generated.
If every row is green, something is wrong with the chart stage.

## C. Run the automated suites yourself (3 minutes, free)

```powershell
python -m pytest tests/ -q                          # expect 15 passed
python scripts\test_failure_modes.py                # expect 12/12 passed
python scripts\audit_ui.py 10163121-c398c4bc        # expect 17/17 passed
python scripts\smoke_test.py                        # expect 171,703 G06Q patents
```

## D. Prove the numbers are real, not typed into a README

This is the part worth doing personally, because it is the thing a judge would
most want to be true and least be able to check.

| # | Command | Cost | Expect |
|---|---|---|---|
| D1 | `python -m priorart.corpus stats --scope G06Q` | free | 171,695 patents, 1976 to 2021 |
| D2 | `bq query --use_legacy_sql=false --project_id=prior-art-agent-2026 < scripts\gate_recall_compare.sql` | free | Old 64d vs new 768d, X @2k 54.0% vs 83.9% |
| D3 | `python -m priorart.eval --n 12 --cats X` | ~$0.20 | X around 97%, control well below it |
| D4 | `python -m priorart.eval --n 40 --cats X,Y` | ~$0.70 | Reproduces the published 97.5 / 92.5 / 18.8 |
| D5 | `python scripts\test_gemini.py` | free | A limitation mapped to a verbatim span |

D3 is the cheap version of D4. Either one demonstrates the headline is
reproducible rather than asserted.

## E. Run the whole thing end to end

| # | Command | Cost | Time |
|---|---|---|---|
| E1 | `python -m priorart.run 10163121 --candidates 200` | ~$1 | ~2 min, local, no Cloud Run |
| E2 | `python -m priorart.orchestrate 10163121 --candidates 2000 --tasks 10` | ~$9 | ~4 min across 10 Cloud Run tasks |

For E2, take the run id it prints and open
`https://nightshift-1015687974010.us-central1.run.app/run/<run_id>` while it is
still going. Watching the tasks light up and the funnel count down is the demo.

**Do not run E2 more than you need to.** It is the main cost in the project.

## F. The ADK agent

```powershell
python scripts\test_agent.py 10163121-c398c4bc
```

Four questions get asked. Watch for the last one: asked whether the patent is
invalid, it must **refuse** and point at the claim chart. If it ever answers that
question directly, that is the single most important thing to fix in this repo.

## G. Watch it run on Google Cloud (for the video)

| # | Where | What |
|---|---|---|
| G1 | https://console.cloud.google.com/run/jobs?project=prior-art-agent-2026 | `nightshift-worker`, its executions, 10 tasks each |
| G2 | Open an execution while E2 is running | Tasks in Running then Succeeded |
| G3 | https://console.cloud.google.com/logs?project=prior-art-agent-2026 | Filter `resource.type="cloud_run_job"` for live worker output |
| G4 | https://console.cloud.google.com/bigquery?project=prior-art-agent-2026 | Dataset `corpus`, the tables, row counts |
| G5 | https://console.cloud.google.com/firestore/databases?project=prior-art-agent-2026 | Database `nightshift`, collection `runs` |

G1 to G3 are the "backend running on Google Cloud" proof the rules require.

## H. Before you submit, logged out

| # | Check |
|---|---|
| H1 | Repo loads in a private window: github.com/JonathanSolvesProblems/nightshift |
| H2 | README renders, tables are not broken |
| H3 | Live URL loads with no sign-in |
| H4 | Video plays with no sign-in |
| H5 | Devpost project page loads in a private window |
| H6 | Read the tagline **aloud** as a stranger. No drafting prose, no options, no brackets |
| H7 | **Search the hackathon gallery for "Nightshift" and confirm it appears** |
| H8 | Screenshot the submission confirmation |

H7 is not optional. A previous entry showed SUBMITTED in the portfolio, returned
HTTP 200 on its own page, and still returned zero results in the hackathon's own
gallery search. Nobody found out until two months later.

## I. Sanity checks on the story itself

Read these out loud and see whether you believe them.

- The tagline in `_submission/submission.md`. Does it say what a person gets?
- The first 20 seconds of `_submission/demo-script.md`. Is there a human in it?
- ACCURACY.md "Scope, stated in full". Is anything hidden that a patent attorney
  would catch?
- Does anything anywhere claim a number the repo cannot regenerate?
