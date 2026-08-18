# Day 1 findings: measured, not assumed

Date: 2026-08-16. Deadline: 2026-08-31 17:00 PDT.

Rule 54 says the un-fakeable work goes first and the architecture gets written
around what the real run reveals. This file records what the real runs revealed
on day 1, before any architecture was committed.

## BigQuery cost surface (measured by dry run, not estimated)

Project `prior-art-agent-2026`, BigQuery sandbox (no billing attached, 1 TB of
query per month free).

Naive queries against `patents-public-data.patents.publications` are not
survivable on the free tier. Measured scan cost for a single-row lookup:

| Query | Scan |
|---|---|
| `claims_localized` for one patent | 116.67 GB |
| `title` + `abstract` + `cpc` + dates for one patent | 228.88 GB |
| `description_localized` for one patent | 1052.42 GB |

One description query consumes the entire monthly free tier. The table is not
partitioned or clustered on `publication_number`, so a `WHERE` filter still
scans the full column. This kills the obvious design of querying the global
publications table per request.

## The tables that actually work

| Table | Rows | Size |
|---|---|---|
| `patentsview.cpc_current` | 45,263,138 | 3.97 GB |
| `patentsview.patent` | 7,905,326 | 5.81 GB |
| `patentsview.claim` | 100,716,530 | 39.45 GB |
| `google_patents_research.vector_db` | 161,272,932 | 79.26 GB |
| `google_patents_research.publications` | 170,418,479 | 470.73 GB |

`patentsview.*` is US-only and normalized, which is why it is an order of
magnitude cheaper than the global flat table. `vector_db` holds a precomputed
`embedding_v1` (repeated FLOAT) keyed by `publication_number` for 161 M
publications, which is the semantic prefilter, already computed, already on
Google Cloud, free to read once.

## The architecture this forces

Materialize once, then query freely. A one-time bootstrap scans
`cpc_current` + `patent` + `claim` + `vector_db` for a single CPC subsection and
writes a working corpus into my own dataset. Every later agent run reads the
small local table instead of the 470 GB global one.

One-time bootstrap cost is roughly 128 GB of the 1 TB monthly allowance, which
leaves headroom for several iterations. This is a real engineering constraint
that produced a real design decision, and both numbers belong in the
architecture diagram.

## Candidate pool size, measured

CPC section G, US patents, distinct patent count by subsection:

| Subsection | Patents |
|---|---|
| G06 (computing, data processing) | 966,046 |
| G01 (measuring, testing) | 567,035 |
| G02 (optics) | 256,943 |
| G11 (information storage) | 232,572 |
| G03 (photography) | 203,411 |

G06 is the classic non-practicing-entity battleground and is the working target.
966,046 is the honest denominator for the "judgment applied at depth" claim.

## Blockers found on day 1

1. **USPTO Open Data Portal API key.** `api.uspto.gov/api/v1/patent/trials/...`
   returns HTTP 401. The legacy open endpoint `developer.uspto.gov/ptab-api/`
   now redirects to the portal SPA and returns HTML, not JSON. A registered
   USPTO.gov account and API key are required. This blocks the PTAB gold-standard
   evaluation, which is the headline number, so it is the highest-priority
   external dependency.

2. **Google Cloud billing quota.** Billing account `016DC5-AFE64A-170023` is at
   its linked-project limit, so `prior-art-agent-2026` has no billing attached.
   BigQuery sandbox works without it. Cloud Run, Pub/Sub, and Vertex AI do not.

3. **No Gemini credentials and no application default credentials** on this
   machine yet.

## What is already proven

- BigQuery reads real patent data from a clean project with no billing.
- The cost surface is measured rather than guessed.
- The prefilter embeddings exist and are free.
- The candidate pool is real and sized.

## Corpus built (executed, not planned)

Scope G06Q, the business-method and e-commerce class where non-practicing
entities actually operate.

| | |
|---|---|
| Patents | 171,695 |
| Grant dates | 1976-01-06 to 2021-09-28 |
| Corpus table | 2.33 GB |
| Embeddings table | 0.08 GB |
| One-time scan spent | 121.87 GB of the 1 TB monthly allowance |
| Storage used | 2.41 GB of the 10 GB free tier |

Target fetches now read the 2.33 GB local table instead of costing 40 GB each.

## Claims coverage, and the honest limit it implies

`patentsview.claim` does not extend into the 2020s. Measured coverage:

| Grant year | Claims coverage |
|---|---|
| 1976 to 2018 | 100% |
| 2019 | 60.9% |
| 2020 onward | 0% |

This matters less than it first appears, because prior art must predate the
target patent's priority date. The correct statement of the limit is:

> For any target patent with a priority date on or before 2018, the corpus
> contains claim text for 100% of the prior art eligible against it.

Targets granted after 2019 are out of scope for this build. That is a real
boundary and it goes in the README rather than being quietly omitted. It does
not bite the actual use case, since patents being asserted in litigation today
were filed years ago.

## Authentication

Browser-based application default credentials failed twice: the consent screen
did not grant the `cloud-platform` scope, and gcloud exited with
"scope is required but not consented". Replaced with a service account key,
which is non-interactive and matches how the service will authenticate on Cloud
Run anyway. The key lives in `.secrets/` and is gitignored.

## Real candidate targets exist

Sample of G06Q patents granted 2006 to 2014 with 15 or more claims, the
non-practicing-entity assertion window:

| Patent | Granted | Claims | Title |
|---|---|---|---|
| 7970722 | 2011-06-28 | 760 | Collaborative decision system |
| 7240025 | 2007-07-03 | 397 | Internet advertising system and method |
| 7096003 | 2006-08-22 | 424 | Transaction security apparatus |

The final demo target will be chosen from PTAB cases once the USPTO key exists,
so that the headline number is graded against a real invalidation outcome
rather than against my own judgment.

## The gold standard is already on BigQuery, and needs no API key

The USPTO Open Data Portal key requires ID.me identity verification, which is
slow and was the single largest schedule risk. It turns out the grading data is
already public on BigQuery, so the headline number is no longer blocked.

`patents-public-data.uspto_ptab.trials_201710`: 7,605 real PTAB trials with
trial number, patent number, prosecution status, patent owner and petitioner.
It includes IPR2012-00001 (Cuozzo, which reached the Supreme Court) and
Intellectual Ventures as a petitioner. `Documents` is metadata only, so decision
text still needs the API, but the case list itself is free.

`patents-public-data.uspto_office_actions_citations.enriched_citations`:
40,384,599 rows, 13.9 GB, covering 2008-04-14 to 2024-05-06 across 2,312,378
applications, of which 22,924,202 references were cited by the examiner rather
than the applicant. Per-row it carries `citedDocumentIdentifier`,
`examinerCitedReferenceIndicator`, `relatedClaimNumberText` (which claims the
reference was cited against) and `passageLocationText` (where in the reference
the relevant passage sits).

Joined against my corpus through `patentsview.application`:

| | |
|---|---|
| Evaluable G06Q patents | **13,419** |
| Examiner citations on them | **132,372** |

This is the eval. For a target patent I hide the file history, run the agent
across the corpus, and measure whether it independently surfaces the reference a
USPTO examiner used to reject a specific claim. The grader is a patent examiner,
not me. It is per-claim, which matches the claim chart output exactly, and
`passageLocationText` even allows checking whether the agent found the right
passage rather than merely the right document.

This replaces "precision 1.000 on my own corpus" with an external, reproducible
number that a judge can re-run.

PTAB remains the rhetorical layer (patents that were actually killed) and the
API key is now a nice-to-have rather than a dependency.

## Clustering, measured rather than assumed

The corpus table was rebuilt clustered on `patent_id`. A dry run reports no
improvement, because dry runs report an upper bound and do not model cluster
pruning. The only honest check is to run the query and read the job statistics
back, which `scripts/bench_clustering.py` does:

| Table | Bytes billed for one target lookup |
|---|---|
| Unclustered | 1,089.0 MB |
| Clustered on `patent_id` | **207.0 MB** |

A 5.3x reduction. Combined with the earlier move off the public tables, a single
target fetch went from 40.16 GB to 0.20 GB, a factor of about 200.

## Gemini access, and the model choice it forces

Listed the models reachable with the hackathon API key. The compliance-relevant
result:

| Model | Available | Input limit |
|---|---|---|
| `gemini-3.5-flash` | yes | 1,048,576 |
| `gemini-3.5-flash-lite` | yes | 1,048,576 |
| `gemini-3.6-flash` | yes | 1,048,576 |
| `gemini-3.7-flash` | yes | 1,048,576 |
| Any 3.5-or-newer Pro | **no** | n/a |

The only Pro models on this key are `gemini-3.1-pro-preview` and
`gemini-pro-latest`. 3.1 is *older* than 3.5, so using Pro would fail the
"Gemini 3.5 or newer" requirement. The pipeline therefore runs on the Flash
family end to end. This is not a compromise: Flash carries a 1M token context,
which is more than enough for claim-by-claim analysis, and it is what makes a
wide judgment stage affordable at all.

## The core primitive works on real claim text

`scripts/test_gemini.py` runs the single operation the whole agent is built from:
given one claim limitation and one candidate reference, decide whether the
reference discloses the limitation, and return the exact supporting span.

Tested against a real limitation from claim 1 of US 7,240,025. The model mapped
"publisher console" to "first interface", "participating web site operator" to
"internet media venue", and "define display constraints" to "input presentation
rules", returning the supporting span rather than a bare yes.

Measured unit cost: **178 input tokens, 104 output tokens** per judgment.

A `responseSchema` is mandatory rather than optional. The first run without one
returned unparseable JSON. At 10,000 candidates per run, a 1% parse failure rate
is 100 silently dropped judgments, which would corrupt the recall number.
