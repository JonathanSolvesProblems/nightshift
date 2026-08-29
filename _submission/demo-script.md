# Demo script, 4:00

Written against the published criteria, which are weighted and specific:

| | | What it actually asks |
|---|---|---|
| Innovation & Operational Utility | **40%** | Autonomous, high-value action. Little to no hand-holding. Not chat |
| Architectural Discipline & Tech Stack | **30%** | Decoupling, state, credentials, failure handling. Not a brittle script |
| Demo & Production Readiness | **30%** | **Live, unedited.** Architecture diagram. Reproducible. Visibly on Google Cloud |

Three consequences, and they override anything in an earlier draft:

1. **The run is started live, on camera.** "Live, unedited" is named in a 30%
   criterion. A finished run replayed is honest but reads as not-live, and the
   page says so in words, so it cannot carry this section.
2. **The architecture gets its own block.** 30% of the score is engineering
   judgement, and no amount of showing the product demonstrates it.
3. **Cuts are signposted out loud.** Unedited does not mean one take; it means
   nothing is hidden. Say "four minutes later" rather than hiding the join.

Every number spoken is produced by the system. Nothing is seeded. The run id is
on screen so a judge can check it.

---

## 0:00 – 0:18 · The problem, as a thing that happens to someone

*A demand letter on a desk. No logo, no title card.*

> A company gets a letter saying it infringes a patent. The first real question
> is whether somebody had already invented the thing.
>
> Most of them never find out. Finding out means a prior-art search: a
> specialist, billed by the hour, over days or weeks. So they settle, because
> looking costs more than folding.

## 0:18 – 0:50 · One action. This is the 40% block.

*Live: the letter uploaded. The steps write themselves. Nothing typed.*

> I hand Nightshift the letter. Not the patent number, the letter.
>
> Gemini reads it and decides three things: whether this is an assertion at all,
> which patent, and who is asserting it. Merrow and Vance Holdings, US
> 10,163,121. I have not typed anything.

*Click "Search this one". The sinking page writes itself, live, no speed ramp.*

> One click, and nothing after it is guided. It splits claim 1 into seven
> limitations. It works out the priority date and drops a hundred and
> twenty-six thousand patents that cannot legally be prior art. Forty-four
> thousand nine hundred survive.
>
> Then it launches ten Cloud Run tasks and starts reading.

## 0:50 – 1:20 · It is really running. This is the 30% demo block.

*Split screen: the core log on the left, the Cloud Run Jobs console on the right,
tasks going from Running to Succeeded. Then the Vertex AI logs.*

> That is the job executing. Ten tasks, each pulling its own shard from
> BigQuery, each calling Gemini once per candidate against every limitation.
>
> It is a background job. I can close the tab; the work is on Cloud Run.

## 1:20 – 1:55 · Why it is built this way. This is the 30% architecture block.

*The architecture diagram, held on screen. **Export it first.** File, Export as,
PNG, 2x, transparent off, with a border. Record the exported image full screen,
not the draw.io editor: the shape palette and format panel are forty percent of
that frame and none of it is the diagram. Hold it still, do not pan.*

> Four decisions worth defending.
>
> The expensive work happens once. One description lookup against the public
> patent tables scans a thousand and fifty-two gigabytes, so the corpus is
> materialized and clustered once. A target fetch went from forty gigabytes to
> two hundred megabytes, measured by dry run before a query ever ran.
>
> The orchestrator and the workers are separate. It ranks once and writes a
> candidate table; the tasks read slices. Retrieval inside each task would
> multiply that scan by ten and buy nothing.
>
> State lives in Firestore. Tasks never talk to each other. Each writes its own
> shard, and whichever finishes last notices everyone is done and closes the run.
>
> And it refuses before it spends. A patent with no claim text gets a sentence,
> not a billed run that cannot find anything.

## 1:55 – 3:00 · The payoff. Longest block, and part of the 40%.

*Cut to the finished run. Say the cut out loud.*

> Four minutes later, two thousand read, thirty-five marked as closest.

*The first claim chart, scrolled slowly.*

> US 7,606,730, filed four years before the priority date. The claim calls
> itself targeted marketing. The reference calls itself a stored value card.
> They share almost no vocabulary, and both describe accumulating loyalty value
> and redeeming it at a point of sale. That is exactly why a keyword search does
> not find it.
>
> [READ THE COUNTS OFF THE RECORDED FRAME. Do not narrate them from here.]
> Some taught outright, some in substance, and some not taught at all, said
> plainly, because a chart with no gaps is not one anyone should trust. Every
> quote is verbatim, so an attorney can go and read it.

*The second chart. This is the strongest moment in the film.*

> A USPTO examiner applied that exact reference against that exact patent. So
> the method works.
>
> But this one is the point. US 6,564,189, filed eight years before the priority
> date, appears nowhere in the examiner's citations, and teaches six of seven
> limitations outright where the examiner's own reference teaches two.
>
> Depth eleven twenty-nine. Nothing that hands a person a shortlist was ever
> going to reach it.

## 3:00 – 3:30 · Who grades it

*The accuracy page.*

> The accuracy number is not mine. The USPTO publishes which references an
> examiner applied in a rejection. So the test is: hide the file history, search
> blind, see whether it re-finds what the examiner used.
>
> Ninety-seven and a half percent on anticipation references, and it stays quiet
> on eighty-one percent of the references the examiner never cited. That second
> number is what makes the first one mean anything.
>
> The one you just saw, that the examiner missed, scores as a miss against me. I
> would rather report it that way than move the goalposts.

## 3:30 – 4:00 · Close

> A specialist billing by the hour over days, against one run, four minutes,
> and thirty-four dollars of Gemini.
>
> It reports what a reference discloses. Whether the claim is invalid is a
> question for a lawyer. This is the evidence that lawyer starts from.

*Repo URL, live URL, run id on screen.*

---

## Shot list, and where each shot comes from

| # | Shot | Source | Status |
|---|---|---|---|
| 1 | Demand letter on a desk | staged prop | to shoot, optional |
| 2 | Letter upload, steps streaming | live, rev 41+ | ✅ clip 4 |
| 3 | Sinking page, live launch | **live run** | **to shoot, ~$34** |
| 4 | Cloud Run Jobs, tasks executing | GCP console | ✅ clip 3 |
| 5 | Vertex AI request logs | GCP console | ✅ clip 3 |
| 6 | Architecture diagram | `docs/architecture.drawio`, exported to PNG | **to shoot, free** |
| 7 | Core log, funnel, seams, cut face | live service | ✅ clips 1 and 4 |
| 8 | Chart, the examiner's reference | live service | ✅ clip 1 |
| 9 | Chart, the reference examiner missed | live service | ✅ clip 1 |
| 10 | Accuracy page | live service | ✅ clip 4 |

Shots 4 and 5 are the "visible proof it runs on Google Cloud" the criteria ask
for by name. Shot 6 is the "clean architecture diagram" they ask for by name.

## Recording the live run

Enable it, record, disable it:

```bash
gcloud run services update nightshift --region us-central1 \
  --project prior-art-agent-2026 --update-env-vars PRIOR_ART_DAILY_RUNS=1
```

Open `/tester?t=<token from .secrets/run-token.txt>` once. The token is then
held in a cookie, so ordinary navigation keeps it. Upload the letter, click
"Search this one", then "Search it again anyway".

**Rehearse the whole film against the finished run first.** It is free and looks
the same apart from the lanes. Roll the live take once.

**Cloud Run takes one to three minutes to place the tasks**, which is dead air
you do not control. Record the launch, stop, and pick up on the finished run.
Say "four minutes later" over the join. That is a signposted cut, not a hidden
one, and it is what "unedited" is protecting against.

## Do not narrate these from the script

The FULL and PARTIAL counts on a chart move between runs. The same reference
charted twice at temperature zero gave 4 and 5 one run, 3 and 4 the next. Read
them off the frame that is actually in the video.

Stable, and safe to say:

- depth 218 of 44,907 eligible, and that an examiner applied that exact reference
- US 6,564,189 at depth 1,129, six of seven, absent from the examiner's citations
- 97.5%, 92.5%, and 81.2% quiet on uncited references
- 171,694 in class, 126,787 dropped, 44,907 eligible, 2,000 read
- about four minutes, about $34

## Rules for the edit

- The emotional peak is the second chart at about 2:40. Never the eval table.
- Never end on the eval page.
- No speed ramping over a terminal or over the placement wait.
- Under 4:00. Only the first four minutes are evaluated. If it runs long, cut
  from the architecture block, never from the charts.
- Cut every frame of run `10002398`. It shows closest art: 0.
- Cut the YouTube tab visible in clip 1 at about 2:33.
- Crop the Windows taskbar out of the file-picker sequence.
