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

Does the vector stage keep the examiner's reference inside the candidate set,
out of 171,695 corpus patents?

The corpus is embedded with **`gemini-embedding-001` at 768 dimensions**.

| Category | n | @1k | @2k | @5k | @10k | median rank |
|---|---|---|---|---|---|---|
| **X** (anticipation) | 124 | 77.4% | **83.9%** | 91.1% | **93.5%** | **128** |
| **Y** (obviousness) | 973 | 59.7% | **67.9%** | 77.3% | **83.7%** | **482** |

Reproduce: `scripts/gate_recall_compare.sql`. The deployed service screens 2,000
candidates, so the @2k column is the production figure.

### The embedding was replaced, and the swap was measured before it was kept

The original prefilter used `embedding_v1` from `google_patents_research`: 64
dimensions, from an unpublished model with no callable endpoint. Both tables are
retained so this comparison stays reproducible.

| Prefilter | Cat | @1k | @2k | @5k | @10k | median rank |
|---|---|---|---|---|---|---|
| `embedding_v1` (64d) | X | 46.8% | 54.0% | 64.5% | 78.2% | 1,230 |
| **`gemini-embedding-001` (768d)** | X | **77.4%** | **83.9%** | **91.1%** | **93.5%** | **128** |
| `embedding_v1` (64d) | Y | 30.4% | 38.7% | 53.4% | 66.3% | 3,961 |
| **`gemini-embedding-001` (768d)** | Y | **59.7%** | **67.9%** | **77.3%** | **83.7%** | **482** |

The median rank of an examiner's anticipation reference fell from 1,230 to 128.

## Result 2: what a shortlist misses, even at full retrieval quality

This is the number the architecture rests on, and it is measured on the *better*
embedding, not the worse one.

| Depth read | X found | Y found |
|---|---|---|
| Top 20 | 26.6% | 15.3% |
| **Top 50** | **40.3%** | **22.8%** |
| Top 100 | 48.4% | 30.4% |
| Top 500 | 71.0% | 50.7% |
| **Top 2,000** | **83.9%** | **67.9%** |

**A top-50 shortlist misses 59.7% of the references a USPTO examiner actually
applied to anticipate a claim, and 77.2% of those applied for obviousness.**

That is the case against the incumbent design in one line. Every commercial
patent search tool ranks a corpus and shows a person the top few dozen results.
Better ranking does not fix this: these figures already use the strongest
embedding available, and the top 50 still misses three of every five killing
references. Reading further down the list is what closes the gap, and reading
2,000 of them is not something a person can do.

## The demo case, end to end

Run `10163121-c398c4bc`, a real Cloud Run execution against real USPTO data.

**Target:** US 10,163,121, "System and method for targeted marketing and consumer
resource management". Filed 2017-10-03, claiming priority to **2006-07-27**.
**What the USPTO did:** during prosecution an examiner applied US 7,606,730,
"System and method for a multiple merchant stored value card", against it as a
category-X anticipation rejection.
**What Nightshift did:** blinded, without ever seeing the file history, it
independently surfaced that same reference.

| | |
|---|---|
| In CPC G06Q | 171,694 |
| Dropped as not prior art | 126,787 |
| Eligible after the priority-date gate | 44,907 |
| Read by Gemini | 2,000 |
| Closest art | 39 |
| **Depth of the examiner's reference** | **218 of 44,907** |
| Wall time | ~4 minutes across 10 Cloud Run tasks |
| Cost | **$9.09** |

Against a professional prior-art search, billed by the hour over days or weeks.

Depth 218 is beyond every shortlist a person is shown. A tool displaying the top
50 misses it; so does one displaying the top 100. That is not an anecdote about
this case, it is the population result above: a top-50 shortlist misses 59.7% of
examiner-applied anticipation references.

The two patents share almost no vocabulary. The claim calls itself targeted
marketing and consumer resource management; the reference calls itself a
multiple merchant stored value card. Both describe accumulating loyalty value
and redeeming it at a merchant point of sale.

This target also demonstrates the eligibility gate on its own. It was **filed in
2017 but claims priority to 2006**, an eleven-year gap. Filtering on filing date
would have searched eleven years of art that is not prior art at all, and the
gate correctly drops 126,787 of 171,694 candidates.

### How this case was chosen

Selected by `scripts/pick_demo_target.py`, which scores candidates rather than
picking one that looks good. It ranks gold pairs where an examiner applied a
category-X reference, computes how deep that reference sits, charts it, and
counts how much of the claim it teaches. Output in `eval/demo-candidates.json`.

The trade is visible in that file, and it got harder after the embedding
upgrade rather than easier. Better retrieval pulls most examiner references
toward the top: the strongest charts in the candidate set now sit at ranks 0, 3,
9 and 16, where ordinary retrieval finds them anyway and the depth argument
collapses. The deepest find (US 10,229,396 at rank 1,129) charts no limitations
as fully taught. This case was chosen because it is deep enough that no shortlist
reaches it and substantial enough that six of seven limitations have a
counterpart.

An earlier version of this document used a different case at depth 548. Under
the upgraded prefilter that same reference ranks 16, so the case no longer
demonstrated anything and was replaced rather than re-described.

### One caveat about the per-limitation counts

The split between "taught outright" and "taught in substance with narrower claim
wording" is not stable across runs. The same reference charted twice against the
same claim, same model, temperature 0, returned FULL 4 / PARTIAL 5 once and
FULL 3 / PARTIAL 4 the next time. It is a judgment call sitting on a boundary.

The counts are therefore reported from whatever run is on screen, and are never
quoted as a fixed property of the pair. What is stable is the depth, the
identity of the reference, and the fact that an examiner applied it.

## Worked example: why depth is the whole point

An early run of this repository returned zero findings. It screened only the top
250 candidates, which was well short of the then-median rank of 1,230 for
category-X references. The fix was not a better prompt. It was reading deeper.

That episode is worth keeping because it is the argument in miniature, and
because the reflex it corrects survives the retrieval upgrade. With
`gemini-embedding-001` the median rank fell to 128, which makes a shallow read
look far more defensible than it is: the median is not the problem. The tail is.
Half of all anticipation references still sit past rank 128, and 59.7% sit past
rank 50.

A better retriever moves the median. It does not remove the need to read the
tail, and the tail is where an examiner's reference is as likely to be as not.

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

## Result 4: end-to-end recall (composed)

The two measured stages multiply. A reference is found only if the prefilter
keeps it and the screener then flags it.

At the 2,000 candidates the deployed service actually screens:

| Category | Prefilter @2k | x Screening | = End to end |
|---|---|---|---|
| X (anticipation) | 83.9% | 97.5% | **81.8%** |
| Y (obviousness) | 67.9% | 92.5% | **62.8%** |

At 10,000:

| Category | Prefilter @10k | x Screening | = End to end |
|---|---|---|---|
| X (anticipation) | 93.5% | 97.5% | **91.2%** |
| Y (obviousness) | 83.7% | 92.5% | **77.4%** |

Read plainly: on four of every five patents where a USPTO examiner found an
anticipating reference, Nightshift independently finds that same reference,
without ever seeing the file history.

The loss is still overwhelmingly in retrieval rather than judgment. At 2,000
candidates the prefilter drops 16.1% of anticipation references before the model
sees them; the model then misses 2.5% of what reaches it. Upgrading the embedding
cut the retrieval loss from 46.0% to 16.1% at that depth, which is why it was
worth doing, and the remaining loss still sits in the same stage.

## Why the eligibility gate is on filing date, not grant date

From a live run against US 10,002,398, the highest ranked finding was
US 10,304,102, which addressed all 8 limitations of claim 1.

| | Filed | Granted |
|---|---|---|
| Target, US 10,002,398 | 2017-09-27 | 2018-06-19 |
| Finding, US 10,304,102 | **2016-01-08** | 2019-05-28 |

The reference was granted almost a year *after* the target and filed almost two
years *before* its priority date. It is valid prior art under §102(a)(2), and a
filter on grant date would have silently discarded the best result in the run.

52.8% of corpus patents claim priority earlier than their own filing date, so
neither grant date nor filing date alone is sufficient. `corpus.dates_g06q`
resolves the earliest of filing date, foreign priority claims, and related US
documents.

## Findings are reported in two tiers

A live run screening 240 candidates against US 10,002,398 returned 145 flagged
references. Reporting that as 145 "material" results would overstate it:

| Tier | Count | Meaning |
|---|---|---|
| Worth reading | 26 | relevance 2+, addresses part of the claimed approach |
| Partial overlap | 119 | relevance 1, same field, does not address the approach |

Screening is deliberately generous, because it decides what gets read closely: a
false positive costs one more model call, while a false negative loses the
reference for good. The ranked tiers, not the raw flagged count, are what the
run page shows and what an attorney would work from.

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
