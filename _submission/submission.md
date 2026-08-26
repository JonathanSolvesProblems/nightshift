# Submission fields

Every section below contains one field and exactly one fenced block holding the
final value. Paste the block. Nothing else in a section is for pasting.

Notes, alternates and reasoning live in NOTES at the bottom of this file, never
above a value.

---

## Project name

```
Nightshift
```

## Elevator pitch

```
Non-practicing entities filed 55.4% of US patent cases last year. Nightshift ranks 171,695 patents, reads the 2,000 closest against every claim limitation, and hands your attorney the prior art that answers the letter, for $9.
```

## Category

```
The Taskmaster
```

## Repository URL

```
https://github.com/JonathanSolvesProblems/nightshift
```

## Hosted project URL

```
https://nightshift-1015687974010.us-central1.run.app
```

## Built with

```
google-cloud, vertex-ai, gemini, cloud-run, bigquery, firestore, python, fastapi, uspto
```

---

## About the project

### Inspiration

```
Non-practicing entities filed 55.4% of US patent cases in 2025, up from 51.8% the year before, and drove 90.3% of high-tech patent litigation (Unified Patents, Patent Dispute Report 2025 in Review). They added 2,236 defendants that year, an 18.7% increase.

Defending is expensive even at the small end. AIPLA puts the median cost of a patent suit with less than $1 million at risk at $600,000, and a case through trial above $3 million.

The first real question in any of those cases is whether the asserted invention was already invented by somebody else. Answering it means a prior-art search: a specialist, billed by the hour, over days or weeks. So the companies most often targeted are precisely the ones for whom looking costs more than folding, and they settle without ever finding out whether the patent would have survived.

I wanted to know what happens to that number if the search runs itself.
```

### What it does

```
You give Nightshift the patent number from a demand letter. It runs unattended and hands your attorney a claim chart: every limitation of claim 1, mapped to the prior art that teaches it, with the supporting passage quoted verbatim from the reference.

It ranks every US patent in the relevant class that predates the asserted patent's priority date, then has Gemini 3.5 Flash actually read thousands of them, one call per candidate, against every limitation. Not a shortlist of fifty for a human to skim. Thousands, read.

The output states what each reference discloses. It never states that a claim is invalid, because that is a question for licensed counsel and ultimately for a court or the PTAB.
```

### How I built it

```
Three stages on Google Cloud.

A Cloud Run service takes the patent number, uses Gemini to split claim 1 into its limitations, applies the prior-art eligibility gate, ranks the eligible corpus in BigQuery by embedding similarity, and writes the ranked candidates into a per-run table.

A Cloud Run Job then fans out across ten tasks. Cloud Run gives each task only its index and the total count, so each derives its own shard with MOD(rank, task_count) = task_index and reads just that slice. Every task calls Gemini 3.5 Flash on Vertex AI once per candidate and writes findings to Firestore the moment it finds them, so a task that dies does not take its results with it and the browser shows progress throughout.

The corpus is 171,695 granted US patents in CPC G06Q plus 413,323 pre-grant publications, materialized once from Google Patents Public Data and PatentsView.

The measured cost surface drove that design. A single description lookup against the public patents table scans 1,052 GB, and one target fetch joining claims scans 40 GB, because those tables are not partitioned or clustered on patent id. Materializing the corpus once and clustering it took a target fetch from 40.16 GB to 0.20 GB, about 200x.
```

### Challenges I ran into

```
The eligibility gate was wrong before it was right. Section 102 turns on filing and priority dates, not grant dates, and 52.8% of patents in the corpus claim priority earlier than their own filing date. In a live run the top finding was granted a year after the target and filed two years before its priority date: valid prior art that a grant-date filter would have silently discarded.

Screening the wrong question cost me a day. An examiner's rejection applies to the claims as they stood at that office action, and the applicant then amends to overcome it, so the issued claim is by construction the version that survived. Asking whether a reference anticipates the issued claim returned zero hits on a pair the examiner had actually applied. Screening now judges materiality; anticipation mapping belongs in the chart.

The AI Studio free tier caps some models at 20 requests a day, which backoff cannot recover from when the unit of work is thousands of candidates. Moving to Vertex AI fixed it.

Every Firestore call inside the container failed with "Invalid database id %28default%29": the parentheses in the default database name were being percent-encoded into the resource path. The same code worked locally. A database whose id has no parentheses avoids it.
```

### Accomplishments that I'm proud of

```
The accuracy number is graded by USPTO examiners, not by me.

The USPTO publishes which references an examiner applied in a rejection, and against which claims. So the test is: hide the file history, run the agent, and see whether it independently re-finds the reference the examiner used.

Blinded, with the reference's number, title, assignee and dates stripped from the prompt: on references an examiner applied to anticipate, it finds them 97.5% of the time (n=40). On references applied for obviousness, 92.5% (n=40). On references the examiner never cited, drawn from the same corpus and passing the same date gate, it stays quiet 81.2% of the time (n=80). That control is what makes the first two numbers mean anything.

And the number that explains why the architecture looks like this. Ranking the corpus with gemini-embedding-001, the strongest embedding available, a top-50 shortlist still misses 59.7% of the references examiners actually applied. Every commercial patent tool ranks a corpus and shows a person the top few dozen results, and no amount of ranking quality rescues that design. Reading 2,000 finds 83.9%.

But the result I am most pleased with is one the scoring counts against me. On the demo patent, the examiner applied US 7,606,730, which teaches two of the seven limitations outright. At depth 1,129 Nightshift found US 6,564,189, filed eight years before the priority date, absent from the examiner's citations entirely, teaching six of seven outright. Because accuracy here is measured against the examiner, that reference is scored as a MISS. The published numbers understate the tool by exactly the amount an examiner's own search understates the art, and I would rather report it that way than move the goalposts.
```

### What I learned

```
That measuring the pipeline in stages is what tells you where to spend.

Splitting recall into "did the prefilter keep the reference" and "did the model then flag it" showed the loss was almost entirely in retrieval: the model was missing 2.5% of what reached it while the prefilter was dropping 46%. That pointed at re-embedding the corpus with gemini-embedding-001, which took anticipation recall at 2,000 candidates from 54.0% to 83.9% and the median rank of an examiner's reference from 1,230 to 128.

It also cost me my favourite demo. The case I had been showing sat at depth 548, and under the better prefilter it ranks 16, so it stopped demonstrating anything and had to be replaced. The honest argument turned out to be stronger than the anecdote: even with the best embedding available, a top-50 shortlist misses 59.7% of examiner-applied references. That is a property of the whole population, not one lucky patent.
```

### What's next for Nightshift

```
Pre-grant publications are 73% of what examiners actually cite, and the corpus holds 413,323 of them but the pipeline does not yet screen them. That is the single largest available gain in recall.

Beyond that: the remaining CPC classes, non-patent literature, and IPR petition grounds under 35 U.S.C. 311(b), which restricts inter partes review to patents and printed publications and therefore makes a patents-first corpus exactly the right shape.
```

---

# NOTES, not for pasting

- Elevator pitch is 195 characters. Leads with the human and the cost, not the
  architecture. The word "troll" appears nowhere in any judged surface; the
  neutral term "non-practicing entity" is used instead, because the rules bar
  disparaging content.
- The pitch says **ranks** 171,695 and **reads** 2,000, and those are different
  verbs on purpose. An earlier version said "reads 171,695 patents overnight",
  which the run page itself contradicts: it shows "read by Gemini: 2,000". The
  tagline is the one sentence most judges read, so it has to survive being
  checked against the screen.
- Every figure above is reproducible from the repo: accuracy from
  `python -m priorart.eval`, prefilter recall from `scripts/gate_recall.sql`,
  demo-case selection from `scripts/pick_demo_target.py`.
- 81.2% quiet is the complement of the measured 18.8% control flag rate. Stated
  as quiet-on-uncited rather than as a false-positive rate because that is the
  direction a reader cares about.
- Before submitting, re-read the pitch in a logged-out private window and confirm
  the project appears in the hackathon gallery search by name. Being marked
  submitted in the portfolio is not proof a judge can find it.
