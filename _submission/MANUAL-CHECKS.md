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
| A1 | [Home](https://nightshift-1015687974010.us-central1.run.app) | Dark mineral page, a patent input, and a second way in below it for the letter | Anything white and SaaS-looking, or a 500 |
| A2 | Home, type `abc`, submit | A page saying that is not a patent number | A stack trace or 500 |
| A3 | Home, type `4000000`, submit | "Cannot search against US 4000000", not in the G06Q corpus | A run starts anyway |
| A4 | [The demo run](https://nightshift-1015687974010.us-central1.run.app/run/10163121-c398c4bc) | The run rail across the top, then the depth column and the funnel | Empty column, or dashes in the counts |
| A5 | Same page, read the rail left to right | 7 → 44,907 → 2,000 → 10 → 2,000 → 39, every stage lit | Any stage dim on a finished run |
| A6 | Same page, hover a green seam in the depth column | Tooltip with patent number, depth, limitations | Nothing |
| A7 | Same page, click a reference in the Seams table | That reference's claim chart | 404 or 500 |
| A8 | [Accuracy](https://nightshift-1015687974010.us-central1.run.app/eval) | X 97.5%, Y 92.5%, control 18.8% | Any cell blank |
| A9 | Switch OS to light mode, reload | Pale mineral stock, deep olive accent, all readable | Anything washed out |
| A10 | Narrow the window to phone width | Rail stacks to two columns, nothing scrolls sideways | A horizontal scrollbar |
| A11 | [A run that has not started](https://nightshift-1015687974010.us-central1.run.app/run/10163121-3ae65353) | Every count filled in | A dash where a count should be |
| A12 | Home, type `10163121`, submit | "This one has been searched", instantly, spending nothing | A new run starts |
| A13 | Home, type `7606730`, submit | A page saying it will not start a new search, with the cost and the CLI command | A new run starts |

A12 and A13 are the spend guard. A13 is the one that matters: the button is
public and unauthenticated, and a new search costs about $34 of Gemini, so it
refuses and explains rather than quietly spending.

A11 is about the opposite case, and it is easier to check on a run you start
yourself (section F). Before a task has read anything, "read by Gemini" and
"closest art" must show a dash, not a zero. A zero there is a finding of none,
which is a different and untrue claim.

Read the tagline on A1 aloud, then check it against A4. It says Nightshift
**ranks** 171,695 and **reads** 2,000, and the run page says "read by Gemini
2,000". Those two have to agree; an earlier version did not.

## B. Give it the letter (2 minutes, free)

The file is in the repo at `docs/demo/demand-letter.pdf` (and `.png`).

| # | Do this | You should see |
|---|---|---|
| B1 | On [Home](https://nightshift-1015687974010.us-central1.run.app), upload `docs/demo/demand-letter.pdf` | US 10163121, sender "Merrow & Vance Holdings LLC", and the quote where it appears |
| B2 | Try the `.png` instead | Same result from a photograph |
| B3 | Upload something that is not a letter, e.g. `docs/shots/demo-run-dark.png` | "No asserted patent found", even though that image is covered in patent numbers |

B3 is the one worth doing. It shows the model is judging whether a document
asserts a patent, not matching digits.

## C. The two claim charts (3 minutes, free)

| # | Link | What it shows |
|---|---|---|
| C1 | [The examiner's reference](https://nightshift-1015687974010.us-central1.run.app/chart/10163121-c398c4bc?ref=7606730) | US 7,606,730 at depth 218. Two limitations taught outright. This is the one a USPTO examiner actually applied |
| C2 | [The one the examiner missed](https://nightshift-1015687974010.us-central1.run.app/chart/10163121-c398c4bc?ref=6564189) | US 6,564,189 at depth **1,129**, filed 1998, absent from the examiner's citations, **six of seven taught outright** |
| C3 | Either chart, scroll to the bottom | At least one row saying the reference does **not** teach a limitation |
| C4 | Either chart, footer | "Not a legal opinion and not a validity determination" |

C2 is the strongest thing in the project. C3 matters more than it looks: a chart
with no gaps reads as generated.

## D. Run the automated suites (3 minutes, free)

```bash
python -m pytest tests/ -q                          # 15 passed
python scripts/test_failure_modes.py                # 12/12 passed
python scripts/audit_ui.py 10163121-c398c4bc        # 17/17 passed
python scripts/smoke_test.py                        # 171,703 G06Q patents
```

## E. Prove the numbers are real

The part worth doing personally: it is what a judge most wants to be true and
least is able to check.

| # | Command | Cost | Expect |
|---|---|---|---|
| E1 | `bq query --use_legacy_sql=false --project_id=prior-art-agent-2026 < scripts/gate_recall_compare.sql` | free | Old 64d vs new 768d: X @2k 54.0% then 83.9% |
| E2 | `python -m priorart.corpus stats --scope G06Q` | free | 171,695 patents, 1976 to 2021 |
| E3 | `python -m priorart.eval --n 12 --cats X` | ~$0.20 | X near 97%, control far below |
| E4 | `python -m priorart.eval --n 40 --cats X,Y` | ~$0.70 | Reproduces 97.5 / 92.5 / 18.8 exactly |
| E5 | `python scripts/make_demo_letter.py` | ~$0.05 | Re-renders the letter and re-extracts 10163121 from both formats |

E1 is free and is the strongest single check.

## F. Watch a run happen (this is the video footage)

The cut face only animates while candidates are being screened. A finished run
shows empty lanes, so the only way to see it is to watch one.

**Reading is public; spending needs the tester link.** A run costs about $34 and
the credit is spent, so `/run` refuses unless the request carries
`PRIOR_ART_RUN_TOKEN`. The token is in `.secrets/run-token.txt`, which is
gitignored and never appears in any tracked file. Your link:

```
https://nightshift-1015687974010.us-central1.run.app/tester?t=<token>
```

That page is the ordinary site with one difference: the search button really
runs, and the page says so, including the price. Everything else, the finished
runs, both charts, the accuracy page and the letter intake, is open at the plain
URL with no link needed.

A daily ceiling of one new run backs the token up, counted in a Firestore
transaction, so even a leaked link cannot spend more than $34 in a day.

**Start from the tester link, not the terminal**, because the browser path is the
one a judge sees. Enter 10163121 on that page (then "Search it again anyway",
since it is already searched), or upload the letter from section B and click
"Search this one".

What should happen, in order:

1. The **sinking page** appears immediately and writes itself line by line over
   about 25 seconds: reading the patent, splitting claim 1 (7 limitations),
   ranking (2,183 MB scanned), the eligibility count (44,907 of 171,694),
   the strata, launching 10 tasks. The last line has a blinking kerf on it.
2. It redirects itself to the core log.
3. The rail sits on stage 4 while Cloud Run places the tasks, and the status
   line under "Cloud Run tasks" reports what Cloud Run itself says, with a
   running clock. **This can take three minutes.** Placement time is Google's,
   not the code's, and the page says which state it is in rather than promising
   a number.
4. Stage 5 goes live and the ten lanes start flowing.

If you would rather not click, the terminal form is the same work:

```bash
python -m priorart.orchestrate 10163121 --candidates 2000 --tasks 10
```

Either way it is **~$34** and about four minutes of reading after placement.
There is a cheaper version at `--candidates 500 --tasks 10` for about $10 if you
only want to see the motion.

**Do not run this more than you need to.** It is the main cost in the project.

## G. The ADK agent

```bash
python scripts/test_agent.py 10163121-c398c4bc
```

Four questions get asked. Watch the last one: asked whether the patent is
invalid, it must **refuse** and point at the claim chart. If it ever answers that
directly, that is the most important thing in this repo to fix.

## H. Google Cloud consoles

| # | Link | What |
|---|---|---|
| H1 | [Cloud Run Jobs](https://console.cloud.google.com/run/jobs?project=prior-art-agent-2026) | `nightshift-worker` and its executions |
| H2 | [Job executions](https://console.cloud.google.com/run/jobs/details/us-central1/nightshift-worker/executions?project=prior-art-agent-2026) | Open one during F: tasks Running then Succeeded |
| H3 | [Logs](https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_run_job%22?project=prior-art-agent-2026) | Live worker output |
| H4 | [BigQuery](https://console.cloud.google.com/bigquery?project=prior-art-agent-2026) | Dataset `corpus`, tables and row counts |
| H5 | [Firestore](https://console.cloud.google.com/firestore/databases?project=prior-art-agent-2026) | Database `nightshift`, collection `runs` |
| H6 | [Cloud Run service](https://console.cloud.google.com/run/detail/us-central1/nightshift/metrics?project=prior-art-agent-2026) | The deployed service and its revisions |
| H7 | [Billing](https://console.cloud.google.com/billing?project=prior-art-agent-2026) | Confirm the $150 credit and current spend |

H1 to H3 are the "backend running on Google Cloud" proof the rules require.

## I. Before you submit, logged out

| # | Link | Check |
|---|---|---|
| I1 | [Repo](https://github.com/JonathanSolvesProblems/nightshift) | Loads in a private window |
| I2 | Same | README renders, tables not broken |
| I3 | [Live URL](https://nightshift-1015687974010.us-central1.run.app) | Loads with no sign-in |
| I4 | Your video URL | Plays with no sign-in |
| I5 | Your Devpost page | Loads in a private window |
| I6 | Same | Read the tagline **aloud** as a stranger. No drafting prose, no options, no brackets |
| I7 | [Gallery](https://allthingsagentichackathon.devpost.com/project-gallery) | **Search "Nightshift" and confirm it appears** |
| I8 | Devpost | Screenshot the submission confirmation |

I7 is not optional. A previous entry showed SUBMITTED in the portfolio, returned
HTTP 200 on its own page, and still returned zero results in the hackathon's own
gallery search. Nobody found out for two months.

## J. Sanity checks on the story

Read these aloud and see whether you believe them.

- The tagline in `_submission/submission.md`. Does it say what a person gets?
- The first 20 seconds of `_submission/demo-script.md`. Is there a human in it?
- ACCURACY.md "Scope, stated in full". Would a patent attorney catch anything hidden?
- Does anything anywhere claim a number the repo cannot regenerate?

## If you only do five

**A1** and **A4** (it works and looks like itself), **B3** (it refuses a document
that is not a demand letter), **C2** (the art the examiner missed, at depth
1,129), **E1** (free, proves the numbers), and **I7** (a judge can find it).
