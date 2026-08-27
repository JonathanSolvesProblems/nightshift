# Demo script, ~4 minutes

Written before recording, per the rule that a script that needs cuts and "let me
also show you" pivots is describing a project too diffuse to win.

Every number spoken here is produced by the system. Nothing is seeded. The run
shown on camera is a real Cloud Run execution against real USPTO data, and the
run id is on screen so a judge can check it.

**Recording rule:** grep the tree for any seed, stub, or fixture before rolling.
If the climax displays anything a script put there rather than the system
produced, fix that before recording anything.

---

## 0:00 – 0:22 · Cold open. No logo, no title card.

*On screen: the demand letter, then the asserted patent number typed in.*

> A patent holding company sends this letter to a forty-person software company.
> It asserts one patent. Before anyone can answer it, somebody has to find out
> whether the invention was already invented. That means a prior-art search: a
> specialist, billed by the hour, over days or weeks.
>
> Most companies that get this letter never ask. They settle, because looking
> costs more than folding.

## 0:22 – 0:40 · One action, then walk away.

*Patent number entered. "Sink a borehole" clicked. The sinking page writes itself
line by line, real time, no speed ramp: claim 1 splits into seven limitations,
44,907 of 171,694 are eligible, ten tasks launch. Cut to the core log page.*

*This is about 25 seconds of screen and it is worth spending, because it is the
only place the pipeline states each stage in words. Do not cut it to a title
card.*

> This is US 10,163,121. Claim 1 breaks into seven limitations, and every US
> patent in this class that predates its priority date is now eligible prior art.
>
> Forty-four thousand of them.

## 0:40 – 1:35 · The engine, live, split screen.

*Left: the core log, funnel counting down, seams appearing at depth, tasks
lighting up. Right: the actual Cloud Run Jobs console and Vertex AI logs.*

> A hundred and seventy-one thousand patents in the class. This one was filed in
> 2017 but claims priority back to 2006, so anything filed after 2006 is not
> prior art against it at all. A hundred and twenty-six thousand of them drop on
> that rule alone.
>
> Forty-four thousand survive. Gemini 3.5 Flash reads two thousand of them, one
> call per patent, against every limitation, spread across ten Cloud Run tasks
> pulling shards from BigQuery.
>
> The bands are the corpus by filing decade. The bright lines are seams: the
> closest art, marked at the depth it was found.

## 1:35 – 1:55 · The async beat.

*Timestamps on screen. Tab closed. Reopened later.*

> This is a background job. Close the tab and it keeps going, because the work
> is running on Cloud Run, not in the browser.

## 1:55 – 3:10 · The payoff. The longest block.

*The claim chart, one row at a time.*

> Here is what it found, and here is why it matters.
>
> US 7,606,730, filed in 2002, four years before this patent's priority date. The
> claim calls itself targeted marketing and consumer resource management. The
> reference calls itself a multiple merchant stored value card. They share almost
> no vocabulary, and both describe accumulating loyalty value and redeeming it at
> a merchant point of sale. That is exactly why a keyword search does not find it.
>
> [READ THE COUNTS OFF THE RECORDED CHART. Do not narrate them from this script.]
> Limitations taught outright. More taught in substance, where the claim recites
> narrower wording than the reference uses. And some the reference does not teach
> at all, said plainly, because a chart with no gaps in it is not a chart anyone
> should trust.
>
> Every quote is copied verbatim out of the reference so an attorney can go and
> read it.

## 3:10 – 3:35 · The turn. This is the strongest thing in the film.

*Cut to the second chart: US 6,564,189 at depth 1,129.*

> That reference was at depth 218, and a USPTO examiner applied that exact
> reference against that exact patent during prosecution. Nightshift found it
> without ever seeing the file history. So the method works.
>
> But this one is the point. US 6,564,189, filed in 1998, eight years before the
> patent's priority date. It appears nowhere in the examiner's citations. And it
> teaches six of the seven limitations outright, where the examiner's own
> reference teaches two.
>
> It sits at depth eleven twenty-nine. Nothing that hands a person a shortlist
> was ever going to reach it.

## 3:35 – 3:50 · The receipt. Fifteen seconds.

*The /eval page.*

> Blinded, across forty cases, it re-finds the examiner's anticipation reference
> ninety-seven and a half percent of the time, and stays quiet on eighty-one
> percent of references the examiner never cited. That second number is what
> makes the first one mean anything.
>
> And those figures are a floor, not an estimate, because they score a reference
> the examiner missed as a miss. Like the one you just saw.

## 3:40 – 4:00 · Close.

> A specialist billing by the hour over days or weeks, against one run and
> thirty-four dollars of Gemini.
>
> It reports what a reference discloses. Whether the claim is invalid is still a
> question for a lawyer. This is the evidence that lawyer starts from.

*Repo URL, live URL, run id on screen.*

---

## Shot list

| # | Shot | Source |
|---|---|---|
| 1 | Demand letter on a desk | staged prop, clearly a prop |
| 2 | Patent number entry, then the sinking page writing itself | live service |
| 3 | Core log, funnel + seams + tasks | live service, real run |
| 4 | Cloud Run Jobs console, tasks executing | GCP console |
| 5 | Vertex AI request logs | GCP console |
| 6 | Claim chart, row by row | live service |
| 7 | /eval accuracy table | live service |

Shots 4 and 5 are the "backend running on Google Cloud" proof the rules require,
and they are also the most interesting shot in the film, which is convenient.

## The per-limitation counts are not stable, and the script must not pretend they are

The same reference charted twice against the same claim, on the same model at
temperature 0, gave FULL 4 / PARTIAL 5 in one run and FULL 3 / PARTIAL 4 in the
next. The split between "taught outright" and "taught in substance" is a judgment
call sitting on a boundary, and it moves.

So the narration never states those two counts from this script. Record the
chart first, read the numbers off the frame that is actually in the video, and
narrate those. A voiceover that says four while the screen says three is the kind
of detail a judge notices and cannot un-notice.

What IS stable, and safe to narrate:

- the depth: 218 of 44,907 eligible
- that a USPTO examiner applied this exact reference against this exact patent
  as an anticipation rejection
- that some limitations are taught, some in substance, and some not at all
- the blinded accuracy figures, which come from a fixed-seed run and do not move

## Cloud Run task placement is not instant, and the recording has to allow for it

Between "launching 10 Cloud Run tasks" and the first lane moving, Cloud Run
places the tasks. That took under a minute on one run and about three on the
next, and none of it is under the code's control. The run page reports the
execution's own state while it waits, so the wait is legible rather than blank,
but it is dead air on camera.

Record the launch and the reading as two takes and cut between them. Do not speed
ramp the wait, and do not narrate a placement time.

## Rules for the edit

- The emotional peak is the chart at roughly 2:30. Never the eval table.
- Never end on the eval page.
- No speed ramping over a terminal. The funnel counting down is the motion.
- Under 4:00. If it runs long, cut from the engine section, never from the chart.
