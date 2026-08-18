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

## Result 2: end-to-end recall

**Status: not yet run.** Scheduled 2026-08-22, reported at whatever n the run
reaches, with the sample pre-registered by fixed seed before the run.

This section will report:

- Blinded arm as the headline: patent number, title, assignee, inventors and
  dates stripped from the prompt.
- A no-retrieval control: the same model asked for prior art with no corpus
  attached, to show recall near zero.
- The per-target table with failures visible, and the miss rate stated.

If the run reaches only n=30, n=30 is what gets published.

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
