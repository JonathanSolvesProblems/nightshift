# Nightshift

**A patent demand letter costs $5,000 and three weeks to answer. Nightshift ranks 171,695 patents, reads the 2,000 closest against every claim limitation, and hands your attorney the answer for $9.**

A law firm quotes $5,000 to $15,000 and one to three weeks to answer one question:
was this patent already invented? Most small companies never ask, because asking
costs more than settling. Nightshift asks, autonomously, in the background.

**Live: https://nightshift-1015687974010.us-central1.run.app**

Built for the All Things Agentic Hackathon, track: **The Taskmaster**.

> **PRIOR ART EVIDENCE DOSSIER, NOT A LEGAL OPINION.**
> Nightshift produces evidence for review by licensed patent counsel. It reports
> what a reference discloses. It does not decide whether a claim is invalid.

---

## Why this exists

Non-practicing entities bring 63% of US patent litigation. 52% of their targets
earn under $25M a year, and the median defendant earns $10.8M. Defending through
trial runs $3M to $5M. The first real question in any of those cases is whether
the asserted patent was already invented by someone else, and answering it is
priced out of reach of exactly the companies most often targeted.

## What makes it different

Every existing tool is a **retrieval** system: it ranks a corpus and shows a
human the top few dozen results.

That design has a ceiling, and it is measurable. Ranking this corpus with
`gemini-embedding-001`, the strongest embedding available, **a top-50 shortlist
still misses 59.7% of the references a USPTO examiner actually applied to
anticipate a claim.** Better ranking does not fix it. Reading further down the
list does.

So Nightshift is a **judgment** system. A vector pass narrows the corpus, then
Gemini reads two thousand candidate references, not fifty, deciding for each one
whether it discloses each limitation of the asserted claim. The prefilter is not
asked to be right. It is only asked not to lose the answer.

| Depth read | Anticipation references found |
|---|---|
| Top 20 | 26.6% |
| **Top 50** (what a person is shown) | **40.3%** |
| Top 100 | 48.4% |
| Top 500 | 71.0% |
| **Top 2,000** (what Nightshift reads) | **83.9%** |

## Measured results

All numbers produced by scripts in this repository against public USPTO data on
BigQuery. Nothing here is seeded or simulated.

### Prefilter recall (the vector stage)

Whether the vector pass keeps the reference an examiner actually applied, out of
171,695 candidates, using `gemini-embedding-001` at 768 dimensions:

| Citation category | n | @1k | @2k | @5k | @10k | median rank |
|---|---|---|---|---|---|---|
| **X** (anticipation, §102) | 124 | 77.4% | **83.9%** | 91.1% | **93.5%** | **128** |
| **Y** (obviousness, §103) | 973 | 59.7% | **67.9%** | 77.3% | **83.7%** | **482** |

This replaced Google Patents' `embedding_v1` (64 dimensions, from an unpublished
model with no callable endpoint) after measuring both on the same gold pairs.
Anticipation recall at 2,000 candidates went from 54.0% to 83.9%, and the median
rank of an examiner's reference from 1,230 to 128. Both tables are kept so the
comparison stays reproducible: `scripts/gate_recall_compare.sql`.

### Does it find what a patent examiner found?

Blinded. The model never saw the reference's patent number, title, assignee or
dates, so it could not lean on anything it may have memorized.

| Set | n | Flagged as material |
|---|---|---|
| **X**, examiner applied as anticipation (§102) | 40 | **97.5%** |
| **Y**, examiner applied as obviousness (§103) | 40 | **92.5%** |
| **Control**, never cited by the examiner | 80 | **18.8%** |

The control is what makes the other two mean anything: recall alone is trivially
gamed by flagging everything, so the same screener was run over references the
examiner did not cite, drawn from the same corpus and passing the same
priority-date gate.

Composed with prefilter recall, at the 2,000 candidates the deployed service
actually screens:

| Category | Prefilter @2k | x Screening | = End to end |
|---|---|---|---|
| X (anticipation) | 83.9% | 97.5% | **81.8%** |
| Y (obviousness) | 67.9% | 92.5% | **62.8%** |

On four of every five patents where a USPTO examiner found an anticipating
reference, Nightshift independently finds that same reference without ever seeing
the file history.

The remaining loss is still in retrieval rather than judgment: at 2,000
candidates the prefilter drops 16.1% of anticipation references before the model
sees them, and the model then misses 2.5% of what reaches it. Upgrading the
embedding cut that retrieval loss from 46.0% to 16.1%, and what is left sits in
the same stage.

Full method, denominators and limits: [`ACCURACY.md`](ACCURACY.md).

### The demo case, end to end

Run `10163121-c398c4bc`, a real Cloud Run execution.

US 10,163,121 "System and method for targeted marketing and consumer resource
management" was prosecuted against US 7,606,730 "System and method for a multiple
merchant stored value card", which a USPTO examiner applied as a category-X
anticipation rejection.

Blinded, without ever seeing the file history, Nightshift independently surfaced
that same reference:

| | |
|---|---|
| In CPC G06Q | 171,694 |
| Dropped as not prior art | 126,787 |
| Eligible after the priority-date gate | 44,907 |
| Read by Gemini | 2,000 |
| Closest art | 39 |
| **Depth of the examiner's reference** | **218** |
| Wall time | ~4 minutes across 10 Cloud Run tasks |
| Cost | **$9.09** |

Against the $5,000 to $15,000 and one to three weeks a firm quotes.

Depth 218 is past every shortlist a person is shown. The two patents share almost
no vocabulary: one calls itself targeted marketing, the other a stored value
card, and both describe accumulating loyalty value and redeeming it at a merchant
point of sale. That is why keyword search misses it and why the judgment stage
has to read rather than match.

The target also demonstrates the eligibility gate by itself. It was **filed in
2017 but claims priority to 2006**. Filtering on filing date would have searched
eleven years of art that is not prior art at all.

The case was chosen by `scripts/pick_demo_target.py`, which scores candidates on
depth and on how much of the claim the chart actually carries, rather than by
picking one that looked good. Scores are in `eval/demo-candidates.json`.

## Scope, stated up front

The eval denominator is disclosed rather than implied, because a recall figure
without its denominator is not a result.

- Gold standard is `citationCategoryCode IN ('X','Y')` from the USPTO office
  action citations dataset: references an examiner **applied in a rejection**,
  not merely listed. Category `A` ("not prejudicial to novelty") is excluded.
- 73% of examiner citations point at pre-grant publications and 6% at non-patent
  literature. A pre-grant corpus of 413,323 G06Q publications is materialized to
  close most of that gap; anything still outside the corpus is excluded from
  numerator and denominator alike.
- Corpus is CPC **G06Q** (business methods, e-commerce), where non-practicing
  entities operate. Cross-class prior art is out of scope.
- Issued claim text in `patentsview.claim` ends in 2019, so targets are drawn
  from earlier grants.
- **This is recall against the examiner, not against ground truth.** An
  examiner's own search recall is itself 45 to 85%, so every reference Nightshift
  finds that the examiner missed scores here as a miss. The number is a floor on
  performance, not an estimate of it.

## Architecture

Measured cost drove the design. Querying the public patents table per request is
not survivable: a single description lookup scans **1,052 GB**, and one target
fetch joining claims scans **40 GB**, because those tables are neither
partitioned nor clustered on patent id.

So the corpus is materialized once and clustered. A target fetch went from
40.16 GB to **0.20 GB**, a factor of about 200.

```
demand letter
  -> target patent + claim limitations
  -> priority-date gate        (references must predate the target)
  -> vector prefilter          BigQuery, 171,695 -> candidates
  -> Gemini judgment fan-out   Cloud Run Jobs + Pub/Sub, thousands of candidates
  -> claim chart               limitation-by-limitation, with pin cites
```

| Component | Service |
|---|---|
| Corpus and prefilter | BigQuery |
| Model | Gemini 3.5 Flash |
| Fan-out workers | Cloud Run Jobs |
| Work distribution | Pub/Sub |
| Run state | Firestore |

## Spin-up

Needs a Google Cloud project with billing attached. Gemini runs on **Vertex AI**,
not the AI Studio endpoint, so no API key is required: the service account
authenticates. (The AI Studio free tier caps some models at 20 requests a day,
which is unusable when the unit of work is thousands of candidates.)

### 1. Project and permissions

```bash
gcloud services enable bigquery.googleapis.com aiplatform.googleapis.com \
  run.googleapis.com firestore.googleapis.com cloudbuild.googleapis.com \
  --project=YOUR_PROJECT

gcloud iam service-accounts create priorart --project=YOUR_PROJECT

for ROLE in bigquery.user bigquery.dataEditor aiplatform.user \
            datastore.user run.developer iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding YOUR_PROJECT \
    --member="serviceAccount:priorart@YOUR_PROJECT.iam.gserviceaccount.com" \
    --role="roles/$ROLE" --condition=None
done

gcloud iam service-accounts keys create key.json \
  --iam-account=priorart@YOUR_PROJECT.iam.gserviceaccount.com

# Firestore needs a NAMED database. The default database id "(default)" is
# percent-encoded into the resource path inside a container and every call fails
# with "400 Invalid database id %28default%29".
gcloud firestore databases create --database=nightshift --location=nam5 \
  --project=YOUR_PROJECT
```

### 2. Local setup

```bash
git clone https://github.com/JonathanSolvesProblems/nightshift.git
cd nightshift
python -m pip install -r requirements.txt

export PRIOR_ART_PROJECT=YOUR_PROJECT
export GOOGLE_APPLICATION_CREDENTIALS=$PWD/key.json
export PYTHONPATH=$PWD/src
```

### 3. Build the corpus

One-time. Every query is dry-run priced first and refuses to run above a
configurable scan ceiling, so nothing here can surprise you with a bill.

```bash
# ~46 GB scanned. Prints the cost and waits.
python -m priorart.corpus bootstrap --scope G06Q --execute

# Filing and priority dates, needed for the prior-art eligibility gate.
bq query --use_legacy_sql=false --project_id=$PRIOR_ART_PROJECT \
  --destination_table=$PRIOR_ART_PROJECT:corpus.dates_g06q --replace \
  --clustering_fields=patent_id < scripts/build_dates.sql

# The evaluation gold set: references examiners applied in real rejections.
bq query --use_legacy_sql=false --project_id=$PRIOR_ART_PROJECT \
  --destination_table=$PRIOR_ART_PROJECT:corpus.gold_pairs --replace \
  < scripts/gold_pairs.sql
```

### 4. Verify

```bash
python scripts/smoke_test.py                      # BigQuery reachable
python -m priorart.corpus stats --scope G06Q      # 171,695 patents
python scripts/test_gemini.py                     # Vertex reachable
python scripts/test_failure_modes.py              # 12 checks
```

### 5. Run it

```bash
# Local, single process.
python -m priorart.run 10163121 --candidates 200

# Distributed, after deploying (below).
python -m priorart.orchestrate 10163121 --candidates 2000 --tasks 10
```

### 6. Deploy

```bash
gcloud builds submit --tag gcr.io/$PRIOR_ART_PROJECT/nightshift:v1

gcloud run jobs create nightshift-worker \
  --image=gcr.io/$PRIOR_ART_PROJECT/nightshift:v1 --region=us-central1 \
  --service-account=priorart@$PRIOR_ART_PROJECT.iam.gserviceaccount.com \
  --command=python --args="-m,priorart.worker" \
  --tasks=1 --max-retries=1 --task-timeout=3600s --memory=1Gi \
  --set-env-vars="PRIOR_ART_PROJECT=$PRIOR_ART_PROJECT"

gcloud run deploy nightshift \
  --image=gcr.io/$PRIOR_ART_PROJECT/nightshift:v1 --region=us-central1 \
  --service-account=priorart@$PRIOR_ART_PROJECT.iam.gserviceaccount.com \
  --allow-unauthenticated --port=8080 --memory=1Gi \
  --set-env-vars="PRIOR_ART_PROJECT=$PRIOR_ART_PROJECT,PRIOR_ART_TASKS=10,PRIOR_ART_CANDIDATES=2000"
```

### Reproduce the published numbers

```bash
python -m priorart.eval --n 40 --cats X,Y        # 97.5% / 92.5% / 18.8%
bq query --use_legacy_sql=false < scripts/gate_recall.sql
python scripts/pick_demo_target.py --pairs 16    # how the demo case was chosen
```

### The ADK agent

```bash
python scripts/test_agent.py <run_id>
```

## Data sources and licensing

- Google Patents Public Data, PatentsView, USPTO Office Action Citations, and
  USPTO PTAB trials, all via `patents-public-data` on BigQuery.
- See [`NOTICES.md`](NOTICES.md) for attribution.

## Documentation

- [`docs/DAY1-FINDINGS.md`](docs/DAY1-FINDINGS.md): the measurements that shaped the design
- [`ACCURACY.md`](ACCURACY.md): end-to-end accuracy
