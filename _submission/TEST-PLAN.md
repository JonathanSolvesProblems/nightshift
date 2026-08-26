# Test plan

Status as of 2026-08-26. Deadline 2026-08-31 17:00 PDT.

`[x]` verified by running it. `[ ]` not yet run. Anything not run is not passing,
regardless of how likely it is to pass.

---

## A. Functional correctness

| | Test | How | Expected |
|---|---|---|---|
| [x] | BigQuery reachable from Python | `python scripts/smoke_test.py` | 171,703 G06Q patents, embeddings present |
| [x] | Target fetch | `python -m priorart.corpus target 7240025` | title, 397 claims, CPC codes |
| [x] | Retrieval + eligibility gate | `python -m priorart.search 10002398` | 158,867 dropped as not prior art, 12,856 eligible |
| [x] | Gemini judgment primitive | `python scripts/test_gemini.py` | maps a limitation, returns the supporting span |
| [x] | Screening on a known examiner pair | `python scripts/diagnose_judge.py 10002398 8433650` | relevant=True, stable across 3 runs |
| [x] | End to end, local | `python -m priorart.run 10002398 --candidates 60` | writes runs/*.json |
| [x] | End to end, distributed | `python -m priorart.orchestrate 10140422 --candidates 2000 --tasks 10` | 10 shards complete, 654 findings |
| [x] | ADK agent tools | `python scripts/test_agent.py <run_id>` | 4 tools called, refuses the validity question |
| [ ] | **Bad input: non-numeric patent** | POST `/run` with `"abc"` | clean error, no 500 |
| [ ] | **Bad input: patent not in G06Q corpus** | `orchestrate 4000000` | LookupError with a readable message, no partial run |
| [ ] | **Bad input: patent with no claims** | a 2020+ grant | refuses before launching a job |
| [ ] | **Worker dies mid-shard** | cancel one task mid-run | other shards finish, findings already written survive |
| [ ] | **Re-run same target** | orchestrate twice | new run id, no collision on the per-run table |
| [ ] | **Chart for a reference with no strong findings** | `/chart/<id>` on a thin run | the "nothing cleared the tier" page, not a 500 |

## B. Accuracy, and whether the numbers reproduce

| | Test | How | Expected |
|---|---|---|---|
| [x] | Gold set builds | `scripts/gold_pairs.sql` | 124 X pairs, 973 Y pairs |
| [x] | Prefilter recall, 64-dim | `scripts/gate_recall.sql` | X 78.2% @10k, Y 66.3% @10k |
| [x] | Screening recall + control | `python -m priorart.eval --n 40 --cats X,Y` | 97.5% / 92.5% / 18.8% control |
| [ ] | **Prefilter recall, 768-dim Gemini** | `scripts/gate_recall_compare.sql` | old vs new on the same pairs |
| [ ] | **Decide: keep or revert the new embedding** | compare @1k/@2k/@5k/@10k | keep only if recall improves |
| [ ] | **Re-run screening eval on the new prefilter** | `python -m priorart.eval --n 40` | confirm judgment quality is unchanged |
| [ ] | **Reproduce ACCURACY.md from a clean shell** | run every command in it | every published number regenerates |
| [ ] | **Seed stability** | run eval twice with the same seed | same sample, comparable rate |

## C. Infrastructure

| | Test | How | Expected |
|---|---|---|---|
| [x] | Cloud Run service serves | curl `/`, `/eval`, `/run/{id}`, `/chart/{id}` | all HTTP 200 |
| [x] | Cloud Run Job executes and shards | `gcloud run jobs executions describe` | 10 tasks, all succeed |
| [x] | Firestore read/write from the container | worker writes findings | findings appear during the run, not after |
| [x] | Run completion is observed | last task closes the run | status leaves "running" |
| [ ] | **Cold start from zero instances** | wait for scale-to-zero, then load `/` | first byte under ~10s, no 5xx |
| [ ] | **Two runs concurrently** | launch 2 orchestrations at once | shards do not cross-contaminate |
| [ ] | **Budget alert exists** | check billing budget | alert set below the credit balance |
| [ ] | **Corpus tables have no expiry** | `bq show` each | expirationTime absent on all |
| [ ] | **Service account has no excess roles** | `get-iam-policy` | only what is needed |

## D. Hackathon compliance

| | Requirement | Evidence |
|---|---|---|
| [x] | Gemini 3.5 or newer | `gemini-3.5-flash` on Vertex AI |
| [x] | Google Agent Framework | GenAI SDK **and** ADK (`src/priorart/agent.py`) |
| [x] | Google Cloud service | BigQuery, Cloud Run Job, Cloud Run Service, Firestore, Cloud Build |
| [x] | Public repo | github.com/JonathanSolvesProblems/nightshift |
| [x] | Spin-up instructions in README | present |
| [x] | Architecture diagram | `docs/ARCHITECTURE.md` |
| [x] | Hosted project URL | live |
| [ ] | **~4-minute demo video** | not recorded |
| [ ] | **Video shows the backend running on Google Cloud** | Cloud Run Jobs console + Vertex logs on camera |
| [ ] | **Category selected on the form** | The Taskmaster |
| [ ] | **Submitted before the deadline** | aim for Aug 29 |

## E. Integrity, run before recording

| | Check | How |
|---|---|---|
| [ ] | **Nothing seeded anywhere** | `git grep -niE "seed_|fixture|stub|mock|dummy|hardcode"` across the tree, then read every hit |
| [ ] | **No hardcoded findings or label arrays** | inspect anything the demo displays |
| [ ] | **Headline number traces to Gemini** | open the file that produced it, confirm the model is in that path |
| [ ] | **No secret in the repo** | `git log -p \| grep -iE "AQ\.|BEGIN PRIVATE KEY|api[_-]?key"` |
| [ ] | **No AI attribution in history** | `git log --format="%B%n%an%n%ae" \| grep -iE "claude\|anthropic\|co-authored"` |
| [ ] | **Every README claim is currently true** | read it line by line against the deployed system |
| [ ] | **Numbers agree across README, ACCURACY.md, the site, and the video** | one pass, all four |

## F. The judge's experience, from a logged-out browser

| | Check |
|---|---|
| [ ] | Repo loads in a private window |
| [ ] | **Clean clone works**: `git clone` into a fresh directory, follow the README exactly, nothing missing |
| [ ] | Hosted URL loads with no auth |
| [ ] | Every route loads: `/`, `/eval`, a run page, a chart page |
| [ ] | A run started from the form actually completes |
| [ ] | Video plays without sign-in |
| [ ] | Project page loads logged out |
| [ ] | **Entry appears in the hackathon gallery search by name** |

## G. Interface

| | Check | How |
|---|---|---|
| [x] | Renders at 1280x720, both themes | `python scripts/shoot.py <run_id>` |
| [ ] | **Light theme contrast** | ink on field, ink3 on well, accent on field, all >= 4.5:1 |
| [ ] | **prefers-reduced-motion** | emulate; descent and settle must not animate |
| [ ] | **Narrow viewport** | 390px wide; column stacks, no horizontal scroll |
| [ ] | **Keyboard only** | tab to the input, submit, follow a finding link |
| [ ] | **Empty states** | a run with zero findings renders a sentence, not a blank panel |
| [ ] | **In-flight state** | load a run page mid-execution; counters and grid populate |

## H. Recording

| | Check |
|---|---|
| [ ] | Demo case re-run on the final prefilter |
| [ ] | Screen recorded at 1280x720 or higher, no scaling artefacts |
| [ ] | Cloud Run Jobs console and Vertex logs captured live |
| [ ] | Per-limitation counts read off the recorded frame, never from the script |
| [ ] | Under 4:00 |
| [ ] | Captions |
| [ ] | Uploaded, public, plays logged out |

---

## Order of work

1. **B**: finish the embedding comparison and decide keep or revert. Everything
   downstream should film the final system.
2. **A**: the six failure-mode tests. These are the ones a judge trips by
   accident, and none have been run.
3. **E**: the integrity sweep, before any recording.
4. **H** then **D**: record, then submit, aiming for Aug 29.
5. **F**: logged-out pass last, after the entry exists.

## Known gaps

There is no automated test suite. Every functional check above is a script run by
hand, which is fine for a build this size but means nothing guards against
regression. If time allows after the video, the highest-value tests to automate
are the eligibility gate (dates are easy to get subtly wrong) and the limitation
label matching (it has already failed once silently).
