# Nightshift

**A non-practicing entity sent you a demand letter. Nightshift reads 171,695 patents overnight and hands your attorney the prior art that answers it, by morning.**

A law firm quotes $5,000 to $15,000 and one to three weeks to answer one question:
was this patent already invented? Most small companies never ask, because asking
costs more than settling. Nightshift asks, autonomously, in the background.

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
human the top few dozen results. Published recall for that approach is 45 to 60%
for keyword search and 70 to 85% for the best semantic search.

Nightshift is a **judgment** system. A coarse vector pass narrows the corpus, and
then Gemini reads thousands of candidate references, not tens, deciding for each
one whether it actually discloses each limitation of the asserted claim. The
prefilter is not asked to be right. It is only asked not to lose the answer.

That trade is measured, not asserted. See below.

## Measured results

All numbers produced by scripts in this repository against public USPTO data on
BigQuery. Nothing here is seeded or simulated.

### Prefilter recall (the vector stage)

Whether the coarse pass keeps the reference a USPTO examiner actually applied in
a rejection, out of 171,695 candidates:

| Citation category | n | recall@1k | @5k | @10k | @25k | median rank |
|---|---|---|---|---|---|---|
| **X** (anticipation, §102) | 124 | 46.8% | 64.5% | **78.2%** | 87.9% | 1,230 |
| **Y** (obviousness, §103) | 973 | 30.4% | 53.4% | **66.3%** | 81.1% | 3,961 |

The embedding is 64-dimensional and would be useless for precision retrieval.
It does not need to be precise. It needs to be a high-recall funnel in front of a
model that reads what survives.

### End-to-end accuracy

See [`ACCURACY.md`](ACCURACY.md).

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

Requires a Google Cloud project with BigQuery enabled and a Gemini API key.

```bash
git clone https://github.com/JonathanSolvesProblems/nightshift.git
cd nightshift
python -m pip install -r requirements.txt

export PRIOR_ART_PROJECT=your-project-id
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
export GEMINI_API_KEY=your-key

# Materialize the corpus. One-time, ~46 GB scanned, prints cost before running.
python -m priorart.corpus bootstrap --scope G06Q --execute

# Verify
python scripts/smoke_test.py
python -m priorart.corpus stats --scope G06Q
```

Every BigQuery call is dry-run priced before execution and refuses to run above a
configurable scan ceiling. The whole corpus build fits inside the free tier.

## Data sources and licensing

- Google Patents Public Data, PatentsView, USPTO Office Action Citations, and
  USPTO PTAB trials, all via `patents-public-data` on BigQuery.
- See [`NOTICES.md`](NOTICES.md) for attribution.

## Documentation

- [`docs/DAY1-FINDINGS.md`](docs/DAY1-FINDINGS.md): the measurements that shaped the design
- [`ACCURACY.md`](ACCURACY.md): end-to-end accuracy
