# Accuracy

Every number here was produced by a script in this repository against public
USPTO data on BigQuery. Nothing is seeded, simulated, or hand-picked.

Last updated: 2026-08-16.

## The gold standard

References a USPTO examiner **applied in a rejection** of the target patent's own
application, taken from
`patents-public-data.uspto_office_actions_citations.enriched_citations`.

The filter is `citationCategoryCode IN ('X','Y')`:

| Code | Meaning | In gold set |
|---|---|---|
| `X` | Claimed invention cannot be considered novel (§102 anticipation) | yes |
| `Y` | Cannot be considered inventive when combined (§103 obviousness) | yes |
| `A` | State of the art, **not prejudicial to novelty** | no |

This distinction matters and is easy to get wrong. The obvious-looking field
`examinerCitedReferenceIndicator` means "listed on the USPTO 892 form", not "used
in a rejection": 67.4% of its rows are category `A`, and it simultaneously omits
1,216,172 category-`X` rows whose indicator is NULL, which is 44% of all
anticipation citations in the dataset. Filtering on it would have built a gold
set that was two thirds non-rejections and missing nearly half the real ones.

Grading is therefore done by a patent examiner, not by the author of this
repository.

## Gold set size

| Category | Pairs | Distinct targets | Distinct references |
|---|---|---|---|
| X (anticipation) | 124 | 123 | 121 |
| Y (obviousness) | 973 | 793 | 934 |

A pair qualifies only if the target and the reference are both inside the G06Q
corpus, both have issued claim text, and both have an embedding.

## Result 1: prefilter recall (measured)

Does the coarse vector stage keep the examiner's reference inside the candidate
set, out of 171,695 corpus patents?

| Category | n | recall@1k | recall@5k | recall@10k | recall@25k | median rank |
|---|---|---|---|---|---|---|
| **X** | 124 | 46.8% | 64.5% | **78.2%** | 87.9% | 1,230 |
| **Y** | 973 | 30.4% | 53.4% | **66.3%** | 81.1% | 3,961 |

Reproduce: `scripts/gate_recall.sql`.

Read this as a ceiling on the full pipeline: the judgment stage can only find
what the prefilter kept. It is also the justification for a wide judgment stage.
Judging the top 100 would cap anticipation recall near 20%; judging 10,000 caps
it at 78.2%.

The embedding is `embedding_v1` from `google_patents_research.vector_db`, 64
dimensions, produced by an unpublished model with no callable endpoint. New text
cannot be projected into that space, so the query vector is the target patent's
own stored vector. A 64-dimensional embedding is far too coarse for precision
retrieval and entirely adequate as a high-recall funnel, which is the whole
architectural argument.

## Worked example: why depth is the whole point

US 10,002,398, "System for facilitating real estate transaction". During
prosecution a USPTO examiner applied US 8,433,650 against it as a category-X
anticipation reference.

Where does that reference sit when the corpus is ranked by similarity to the
target?

| | |
|---|---|
| Eligible prior art after the priority-date gate | 149,721 |
| Rank of the reference the examiner actually used | **6,426** |

A tool that ranks the corpus and shows a human the top 50 does not surface this
reference. Neither does one that shows the top 500. It is only found by a system
willing to actually read several thousand candidates, which is what separates a
judgment pipeline from a retrieval pipeline.

This is also why an early run of this repository returned zero hits: it screened
only the top 250, which is well short of the measured median rank of 1,230 for
category-X references. The fix was not a better prompt. It was screening deeper.

## Model selection, measured rather than assumed

Screening runs on `gemini-3.5-flash`. Two alternatives were tested against the
same known category-X pair and rejected on evidence.

| Model | Behaviour across repeated runs at temperature 0 |
|---|---|
| `gemini-3.5-flash` | stable, 3 of 3 runs identical |
| `gemini-3.5-flash-lite` | **unstable**: one run found 4 limitations, the next found 0 |
| any Pro model | not available at 3.5 or newer, so it would fail the version requirement |

flash-lite costs less per token and would have cut the bill for a wide pass by a
useful margin. It is not usable here, because instability in the screening stage
does not degrade the recall number gracefully, it makes it meaningless: the same
reference would be found or missed depending on which run you happened to
measure.

Vertex AI is the runtime rather than the AI Studio endpoint. The AI Studio free
tier caps some models at 20 requests per day, which is not a limit that backoff
can recover from when the unit of work is thousands of candidates.

## Result 2: screening recall, with a negative control (measured)

Blinded. The model never saw the reference's patent number, title, assignee, or
dates, so it could not lean on anything it may have memorized about a well-known
patent. Sample drawn by fixed seed `nightshift-2026-08-25` before the run.

| Set | n | Flagged as material |
|---|---|---|
| **X**, examiner applied as anticipation (§102) | 40 | **97.5%** |
| **Y**, examiner applied as obviousness (§103) | 40 | **92.5%** |
| **Control**, never cited by the examiner | 80 | **18.8%** |

Reproduce: `python -m priorart.eval --n 40 --cats X,Y`. Cost $0.67, 696 seconds.
Raw per-pair results in `eval/screening.json`.

The control is the number that makes the other two mean anything. Recall alone is
trivially gamed by flagging everything, so the same screener was run over
references the examiner did **not** cite, drawn from the same corpus, the same
CPC class, and passing the same priority-date gate. These are plausible
neighbours, not random junk, which is why 18.8% is the honest figure rather than
something near zero.

## Result 3: end-to-end recall (composed)

The two measured stages multiply. A reference is found only if the prefilter
keeps it and the screener then flags it.

| Category | Prefilter @10k | x Screening | = End to end @10k |
|---|---|---|---|
| X (anticipation) | 78.2% | 97.5% | **76.2%** |
| Y (obviousness) | 66.3% | 92.5% | **61.3%** |

Read plainly: on roughly three of every four patents where a USPTO examiner
found an anticipating reference, Nightshift independently finds that same
reference, without ever seeing the file history.

The loss is almost entirely in retrieval, not in judgment. The 64-dimensional
prefilter drops 21.8% of anticipation references before the model ever reads
them, while the model itself misses only 2.5% of what reaches it. That is the
argument for screening deeper rather than for a better prompt.

## What the false-positive rate costs

At an 18.8% control rate, screening 10,000 candidates flags roughly 1,900
references. Nobody hands an attorney 1,900 documents. Screening decides what gets
read closely; the ranked relevance score and the chart stage decide what is worth
presenting, and the chart is where limitation-by-limitation evidence is produced.
The recall figures above survive that narrowing because ranking reorders the
flagged set, it does not discard it.

## Known limits

- Recall is measured against the examiner, not against ground truth. An
  examiner's own recall is 45 to 85%, so references Nightshift finds that the
  examiner missed are scored here as misses. This number is a floor.
- 73% of examiner citations point at pre-grant publications, 6% at non-patent
  literature. Both are outside the granted-patent corpus and are excluded from
  numerator and denominator alike.
- Corpus is CPC G06Q only. Cross-class prior art is unreachable by construction.
- `relatedClaimNumberText` records claims pending at the office-action date, not
  as issued, so claim-level mapping is reported as agent output and is never
  scored as a corroborated quantity.
