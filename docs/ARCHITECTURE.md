# Architecture

Nightshift is a background job, not a request/response service. One request starts
it, many Cloud Run tasks execute it, and a browser watches it from outside. The
shape of the system follows from that, and from one measured constraint.

## The constraint that decided the design

Querying the public patents tables per request is not survivable. Measured by dry
run, not estimated:

| Query against `patents-public-data` | Scan |
|---|---|
| One `description` lookup | **1,052 GB** |
| One `claims` lookup | 117 GB |
| One target fetch joining `patentsview.claim` | 40 GB |

Those tables are neither partitioned nor clustered on patent id, so a `WHERE`
filter still reads the whole column. So the corpus is materialized once into a
clustered table and every later read hits that instead.

| | Before | After |
|---|---|---|
| One target fetch | 40.16 GB | **0.20 GB** |

About 200x, from two changes: moving off the public tables, then clustering on
`patent_id`. Both are measured in `docs/DAY1-FINDINGS.md`.

## Flow

```mermaid
flowchart TB
    U([Patent number from a demand letter]) --> W

    subgraph SVC["Cloud Run service: nightshift"]
        W["Orchestrator<br/>splits claim 1 into limitations"]
    end

    W -->|"Gemini 3.5 Flash"| V1[["Vertex AI"]]
    W --> BQ

    subgraph BQ["BigQuery"]
        C1["corpus.patents_g06q_clustered<br/>171,695 granted patents"]
        C2["corpus.pregrant_g06q<br/>413,323 published applications"]
        C3["corpus.vectors_g06q<br/>64-dim embeddings"]
        C4["corpus.dates_g06q<br/>filing + priority dates"]
        RT["corpus.run_&lt;id&gt;<br/>ranked candidates for this run"]
    end

    C4 -.->|"priority-date gate<br/>drops references that<br/>are not prior art"| RT
    C3 -.->|"cosine rank"| RT

    W --> J

    subgraph J["Cloud Run Job: nightshift-worker"]
        T0["task 0"]
        T1["task 1"]
        T2["task ..."]
        T3["task N"]
    end

    RT -->|"MOD(rank, N) = task_index"| J
    J -->|"reads each candidate<br/>against every limitation"| V1
    J --> FS[("Firestore<br/>run state, shard progress,<br/>findings as they land")]
    FS --> UI["/run/&lt;id&gt; live funnel<br/>/chart/&lt;id&gt; claim chart<br/>/eval accuracy"]
```

## Why each piece is there

**BigQuery** holds the corpus and does the ranking. The embedding prefilter is a
cosine rank over 171,695 stored vectors, which is a database operation, not a
model operation.

**Vertex AI** runs `gemini-3.5-flash`. It is the engine, not an advisor: the
model decides which references are material and produces the limitation-by-
limitation mapping. Vertex rather than the AI Studio endpoint because the free
tier caps some models at 20 requests per day, which backoff cannot recover from
when the unit of work is thousands of candidates.

**Cloud Run Jobs** execute the fan-out. Tasks receive `CLOUD_RUN_TASK_INDEX` and
`CLOUD_RUN_TASK_COUNT` and nothing else, so the shard boundary is derived from
the index alone. The orchestrator materializes the ranked candidates once and
each task reads `MOD(rank, task_count) = task_index`. Running retrieval inside
every task is the obvious design and the wrong one: it multiplies a 1.3 GB scan
by the worker count and buys nothing.

**Firestore** is where the three parties meet. The job is started by one request,
executed by tasks that never talk to each other, and watched by a browser that
may connect long after the work began. Findings are written the moment they are
found, so a task that dies does not take its results with it.

## The funnel

Every number below is produced by the system, and the same numbers appear on
`/run/{id}` while a run is in flight.

```
171,723   corpus
          |  priority-date gate: a reference must predate the
          |  target's earliest priority date. 52.8% of corpus
          |  patents claim priority earlier than their own filing
          |  date, so grant date is wrong for over half of them.
 -158,867  not prior art
          |  family exclusion: shared title or shared priority date
  12,856  eligible
          |  cosine rank over 64-dim stored embeddings
   2,000  read by Gemini, one call per candidate
          |  materiality screen
     ~40  material
          |  limitation-by-limitation mapping
      10  charted
```

Numbers shown are an actual run against US 10,002,398.

## The one number that explains the shape

For US 10,002,398 the reference a USPTO examiner actually applied as a
category-X anticipation rejection sits at **rank 6,426 of 149,721** eligible
references.

A tool that ranks the corpus and shows a human the top 50 never surfaces it.
Neither does one that shows the top 500. It is only found by a system willing to
read several thousand candidates, which is the difference between a retrieval
pipeline and a judgment pipeline, and the reason the fan-out exists at all.
