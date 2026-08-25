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
A patent troll's demand letter costs $5,000 and three weeks to answer. Nightshift reads 171,695 patents overnight and hands your attorney the prior art that answers it by morning.
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
Non-practicing entities bring 63% of US patent litigation, and 52% of the companies they target earn under $25 million a year. The median defendant earns $10.8 million. Defending through trial runs $3 to $5 million.

The first real question in any of those cases is whether the asserted invention was already invented by somebody else. Answering it means a prior-art search, and a law firm quotes $5,000 to $15,000 and one to three weeks for one. So the companies most often targeted are precisely the ones for whom looking costs more than folding, and they settle without ever finding out whether the patent would have survived.

I wanted to know what happens to that number if the search runs itself.
```

### What it does

```
You give Nightshift the patent number from a demand letter. It works overnight and hands your attorney a claim chart: every limitation of claim 1, mapped to the prior art that teaches it, with the supporting passage quoted verbatim from the reference.

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

And the number that explains why the architecture looks like this: in the demo case, the reference the examiner actually applied sits at depth 548 out of 100,104 eligible references. Nothing that shows a human the top fifty results finds it.
```

### What I learned

```
Retrieval quality was never the bottleneck I assumed it was. The prefilter is a 64-dimensional embedding, far too coarse to rank prior art precisely, and it still keeps 78.2% of anticipation references inside the top ten thousand. The judgment stage then misses only 2.5% of what reaches it.

So the loss is almost entirely in retrieval, and the fix is not a better ranker. It is reading further down the list than anyone bothers to.
```

### What's next for Nightshift

```
Pre-grant publications are 73% of what examiners actually cite, and the corpus holds 413,323 of them but the pipeline does not yet screen them. That is the single largest available gain in recall.

Beyond that: the remaining CPC classes, non-patent literature, and IPR petition grounds under 35 U.S.C. 311(b), which restricts inter partes review to patents and printed publications and therefore makes a patents-first corpus exactly the right shape.
```

---

# NOTES, not for pasting

- Elevator pitch is 191 characters. Leads with the human and the cost, not the
  architecture. "Patent troll" appears here and nowhere in the judged repo or
  video, where the neutral term "non-practicing entity" is used instead, because
  the rules bar disparaging content.
- Every figure above is reproducible from the repo: accuracy from
  `python -m priorart.eval`, prefilter recall from `scripts/gate_recall.sql`,
  demo-case selection from `scripts/pick_demo_target.py`.
- 81.2% quiet is the complement of the measured 18.8% control flag rate. Stated
  as quiet-on-uncited rather than as a false-positive rate because that is the
  direction a reader cares about.
- Before submitting, re-read the pitch in a logged-out private window and confirm
  the project appears in the hackathon gallery search by name. Being marked
  submitted in the portfolio is not proof a judge can find it.
