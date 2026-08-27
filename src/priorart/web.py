"""Cloud Run service: start runs, watch them, read the result.

DESIGN CODE. Read this before changing any value below.

Category convention avoided: every patent and legal-tech tool (Patlytics,
IPRally, XLSCOUT, Derwent, Anaqua) ships a white enterprise-SaaS canvas, a left
sidebar of icon+label rows, a corporate-navy accent, dense zebra-striped Inter
tables, and search results as white cards each carrying a coloured
relevance-score chip. The AI-agent variant adds an indigo-to-violet gradient
hero and a dark console tab. Adopting that look concedes the argument this tool
is making.

Metaphor: a core sample drawn from a borehole through the patent record. Depth
is time, older art lies deeper, and the reference that matters is a seam at a
measured depth.

  - The corpus is one continuous banded column with no gaps between bands,
    because prior art is a continuous record in time and cutting it into cards
    would imply the entries are independent.
  - Vertical position encodes rank and band temperature encodes filing decade,
    because the product's whole claim is that the answer sits at a depth no
    human search reaches, and that has to be visible rather than asserted.
  - There is exactly one accent, reserved for a reference judged worth an
    attorney's time, because in every run most of the column is not.
  - Numerals are tabular and every count sits in the same column position,
    because the funnel numbers only mean anything as a subtraction.

Full spec in .design/manifest.json.
"""

from __future__ import annotations

import json
import os
import time

from google.cloud import run_v2

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    StreamingResponse,
)

from . import judge, orchestrate, store

app = FastAPI(title="Nightshift")

DEFAULT_TASKS = int(os.environ.get("PRIOR_ART_TASKS", "10"))
DEFAULT_CANDIDATES = int(os.environ.get("PRIOR_ART_CANDIDATES", "2000"))
# Starting a new search costs about thirty-four dollars of Gemini, and the
# hackathon credit that paid for the runs already recorded is spent. So the
# public deployment reads: every finished run, every chart and the letter intake
# stay open, and starting a NEW billed search is off unless someone deliberately
# turns it on for a recording session.
#
#   gcloud run services update nightshift --region us-central1 \
#     --update-env-vars PRIOR_ART_DAILY_RUNS=1
#
# Zero is the default rather than a large number because the endpoint is public
# and unauthenticated, and a ceiling that depends on nobody finding the button is
# not a ceiling.
DAILY_RUN_CAP = int(os.environ.get("PRIOR_ART_DAILY_RUNS", "0"))
# Reading a letter is one Gemini vision call, about a cent. Bounded anyway,
# because "about a cent" times a crawler is not about a cent.
DAILY_LETTER_CAP = int(os.environ.get("PRIOR_ART_DAILY_LETTERS", "200"))

FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Instrument+Sans:wght@400;500;600&"
    "family=Martian+Mono:wght@400;600&display=swap"
)

CSS = """
:root{
  --field:#262B29; --well:#1D2220; --raised:#2F3533; --hairline:#3A413E;
  --ink:#E8EAE6; --ink2:#A8AFA9; --ink3:#6F7873;
  --seam:#8CBF3F; --seam-ink:#1A1F18;
  --s1:6px; --s2:12px; --s3:20px; --s4:32px; --s5:52px;
  --settle:420ms; --ease:cubic-bezier(.22,.61,.36,1);
}
@media (prefers-color-scheme: light){
  :root{
    --field:#D8DBD5; --well:#C6CAC3; --raised:#E4E7E1; --hairline:#B0B5AC;
    /* ink3 is darker than its dark-theme counterpart on purpose: against the
       light well it measured 2.74:1, under the 3:1 floor. Both palettes are
       designed, not inverted, so the tertiary tone is not the same value. */
    --ink:#1F2422; --ink2:#4C5451; --ink3:#565E5A;
    --seam:#4F7318; --seam-ink:#F2F5EE;
  }
}
*{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--field);color:var(--ink);
  font:15px/1.5 "Instrument Sans",ui-sans-serif,system-ui,sans-serif;
  padding:var(--s4) var(--s3);max-width:1140px;margin:0 auto;
}
a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--hairline)}
a:hover{border-bottom-color:var(--seam)}
.num{font-family:"Martian Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;
  font-feature-settings:"tnum" 1;letter-spacing:-.04em}

/* masthead: a core log header, not a nav bar */
header{border-bottom:2px solid var(--ink);padding-bottom:var(--s2);margin-bottom:var(--s3)}
.mark{font-size:13px;letter-spacing:.34em;text-transform:uppercase;font-weight:600}
.mark b{font-weight:600}
.mark span{color:var(--ink3);font-weight:400}
.sub{color:var(--ink2);font-size:13px;margin-top:var(--s1);max-width:66ch}

/* the well: everything structural is milled into the field, never floated on it */
.well{background:var(--well);border:1px solid var(--hairline);
  box-shadow:inset 0 1px 0 rgba(0,0,0,.28);padding:var(--s3);margin-top:var(--s3)}
.lip{border-top:1px solid var(--hairline);margin-top:var(--s3);padding-top:var(--s3)}
h2{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--ink3);
  font-weight:600;margin-bottom:var(--s2)}

/* the funnel reads as a subtraction, so counts share one right-aligned column */
.funnel{display:grid;grid-template-columns:1fr auto;gap:var(--s1) var(--s3);align-items:baseline}
.funnel dt{color:var(--ink2);font-size:13.5px}
.funnel dd{text-align:right;font-size:17px}
.funnel .minus dd{color:var(--ink3)}
.funnel .minus dd::before{content:"\\2212";margin-right:.35em;color:var(--ink3)}
.funnel .keep{border-top:1px solid var(--hairline);padding-top:var(--s1);margin-top:var(--s1)}
.funnel .keep dt,.funnel .keep dd{color:var(--ink);font-weight:600}
.funnel .found dd{color:var(--seam)}

/* the depth column: the one loud element on the page */
.rig{display:grid;grid-template-columns:168px 1fr;gap:var(--s4)}
.core{position:relative;background:var(--well);border:1px solid var(--hairline);
  box-shadow:inset 0 2px 5px rgba(0,0,0,.4);min-height:480px;overflow:hidden}
.band{position:absolute;left:0;right:0}
/* The cut face: a light scrim over ground already read, with a bright kerf at
   the working depth. Not a fill, because the strata under it must stay legible. */
.drill{position:absolute;left:0;right:0;top:0;background:rgba(0,0,0,.16);
  border-bottom:2px solid var(--seam);transition:height var(--settle) var(--ease)}
/* Only references worth an attorney's time are cut as seams. An earlier version
   drew every flagged candidate and 231 of them turned the column into a barcode
   that hid the strata entirely. */
.seam{position:absolute;left:0;right:0;height:3px;background:var(--seam);
  box-shadow:0 0 0 1px rgba(0,0,0,.55);transition:top var(--settle) var(--ease)}
.seam.deepest{height:5px}
.seam.deepest::after{content:"";position:absolute;right:-7px;top:-3px;
  border:5px solid transparent;border-right-color:var(--seam)}
.ruler{position:relative;min-height:480px;color:var(--ink3);font-size:10.5px}
.tick{position:absolute;left:0;white-space:nowrap}
.corewrap{display:grid;grid-template-columns:1fr 52px;gap:var(--s2)}

/* The drill string: the pipeline as stages of a rig, surface to bit.
   Every value on it is read from the run, and a stage only lights when that
   stage has actually done something. Nothing here animates on a timer. */
.string{display:grid;grid-template-columns:repeat(6,1fr);gap:0;margin-top:var(--s2);
  border:1px solid var(--hairline);background:var(--well);
  box-shadow:inset 0 2px 5px rgba(0,0,0,.35)}
.stg{position:relative;padding:var(--s2) var(--s2) var(--s2) var(--s3);
  border-right:1px solid var(--hairline);opacity:.34;
  transition:opacity 420ms var(--ease),background 420ms var(--ease)}
.stg:last-child{border-right:0}
.stg.live{opacity:1;background:rgba(140,191,63,.05)}
.stg.done{opacity:1}
.stg-n{font:600 20px/1.1 "Martian Mono",ui-monospace,monospace;
  font-variant-numeric:tabular-nums;letter-spacing:-.04em}
.stg.live .stg-n{color:var(--seam)}
.stg-l{color:var(--ink3);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;
  margin-top:5px;line-height:1.35}
/* the bit: a mark that travels to whichever stage is currently cutting */
.stg::before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;
  background:var(--seam);transform:scaleY(0);transform-origin:top;
  transition:transform 420ms var(--ease)}
.stg.live::before,.stg.done::before{transform:scaleY(1)}
.stg.live::after{content:"";position:absolute;left:-1px;top:0;bottom:0;width:2px;
  background:var(--seam);animation:cut 1.6s ease-in-out infinite}
@keyframes cut{0%,100%{opacity:.25}50%{opacity:1}}

/* The cut face. Every particle is a candidate that was actually screened and
   every lane is a real Cloud Run task, so the flow rate is the job's rate. When
   the run finishes the canvas empties and stops; it is a window onto work, not
   a loading spinner. */
.flowwrap{position:relative;margin-top:var(--s2);border:1px solid var(--hairline);
  background:var(--well);box-shadow:inset 0 2px 5px rgba(0,0,0,.35)}
#flow{display:block;width:100%;height:190px}
.flowlab{position:absolute;left:var(--s2);top:var(--s1);color:var(--ink3);
  font-size:9.5px;letter-spacing:.14em;text-transform:uppercase}
.flowlab.r{left:auto;right:var(--s2)}

/* shard tasks: witness marks, not status pills */
.tasks{display:flex;flex-wrap:wrap;gap:3px;margin-top:var(--s2)}
.tk{width:100%;max-width:22px;height:8px;background:var(--raised);
  border:1px solid var(--hairline)}
.tk.run{background:var(--ink3)}
.tk.done{background:var(--seam);border-color:var(--seam)}

/* the sinking page: streamed, one line per stage as it lands.
   The live marker is :last-child rather than script, because the browser
   re-evaluates it every time another line arrives over the wire. */
.steps{list-style:none;margin:var(--s3) 0 0;padding:0;font-size:13.5px;line-height:2.15}
.steps li{color:var(--ink2);padding-left:22px;position:relative;
  animation:land var(--settle) var(--ease) both}
.steps li::before{content:"";position:absolute;left:0;top:.95em;
  width:11px;height:1px;background:var(--ink3)}
.steps li.fact{color:var(--ink)}
.steps li.fact::before{background:var(--seam);height:3px;top:.85em}
.steps li:last-child::after{content:"";display:inline-block;width:6px;height:11px;
  margin-left:8px;background:var(--seam);vertical-align:-1px;
  animation:kerf 1.05s steps(2,end) infinite}
@keyframes kerf{0%{opacity:1}50%{opacity:0}100%{opacity:1}}
@keyframes land{from{opacity:0;transform:translateY(-3px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion: reduce){
  .steps li{animation:none}
  .steps li:last-child::after{animation:none}
}

table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--ink3);font-weight:600;padding:var(--s1) var(--s2) var(--s1) 0;
  border-bottom:1px solid var(--hairline)}
td{padding:10px var(--s2) 10px 0;border-bottom:1px solid var(--hairline);vertical-align:top}
tr:last-child td{border-bottom:0}
td.n{white-space:nowrap}
.tier{font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink3)}
.tier.hot{color:var(--seam)}

/* controls are the only place radius appears: roundness marks interactivity */
input[type=text]{background:var(--field);border:1px solid var(--hairline);
  color:var(--ink);border-radius:3px;padding:11px var(--s2);width:250px;
  font:15px "Instrument Sans",sans-serif}
input[type=text]:focus{outline:2px solid var(--seam);outline-offset:1px}
button{background:var(--seam);color:var(--seam-ink);border:0;border-radius:3px;
  padding:11px var(--s3);font:600 14px "Instrument Sans",sans-serif;cursor:pointer;
  letter-spacing:.02em}
button:hover{filter:brightness(1.08)}
button:focus-visible{outline:2px solid var(--ink);outline-offset:2px}

/* the letter drop: a second way in, deliberately quieter than the first */
.drop{margin-top:var(--s3);padding-top:var(--s3);border-top:1px dashed var(--hairline);
  display:flex;flex-wrap:wrap;gap:var(--s2);align-items:center}
.drop span{color:var(--ink2);font-size:13px;width:100%}
.drop input[type=file]{color:var(--ink2);font:13px "Instrument Sans",sans-serif;
  max-width:100%}
.drop input[type=file]::file-selector-button{background:var(--field);
  border:1px solid var(--hairline);color:var(--ink);border-radius:3px;
  padding:8px var(--s2);margin-right:var(--s2);cursor:pointer;
  font:13px "Instrument Sans",sans-serif}
.drop button{background:transparent;color:var(--ink);border:1px solid var(--seam);
  padding:9px var(--s3)}
.drop button:hover{background:var(--seam);color:var(--seam-ink);filter:none}

.note{color:var(--ink3);font-size:12.5px;line-height:1.6;margin-top:var(--s2);max-width:74ch}
.caveat{border-left:2px solid var(--ink3);padding-left:var(--s2);color:var(--ink2);
  font-size:12.5px;margin-top:var(--s3);max-width:74ch}

/* the chart is the deliverable: it is set to be read, not skimmed */
.exhibit{background:var(--well);border:1px solid var(--hairline);margin-top:var(--s3)}
.exhibit-head{padding:var(--s3);border-bottom:2px solid var(--ink)}
.lim{display:grid;grid-template-columns:190px 1fr;gap:var(--s3);
  padding:var(--s3);border-bottom:1px solid var(--hairline)}
.lim:last-child{border-bottom:0}
.lim-id{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink3);
  font-weight:600;margin-bottom:var(--s1)}
.lim-text{color:var(--ink2);font-size:13px;line-height:1.55}
.quote{border-left:2px solid var(--seam);padding-left:var(--s2);font-size:13.5px;
  line-height:1.6;margin-bottom:var(--s2)}
.quote.partial{border-left-style:dashed}
.quote.absent{border-left-color:var(--ink3);color:var(--ink3);font-style:italic}
.level{font-size:10px;letter-spacing:.16em;text-transform:uppercase;font-weight:600;
  margin-bottom:var(--s1);color:var(--seam)}
.level.partial{color:var(--ink2)}
.level.absent{color:var(--ink3)}
.why{color:var(--ink2);font-size:12.5px;line-height:1.55}

/* Wide content scrolls inside its own container. The seam table has six columns
   and the page body must never scroll sideways to accommodate it. */
.scroller{overflow-x:auto;-webkit-overflow-scrolling:touch}
.scroller table{min-width:620px}

@media (max-width:760px){
  .rig{grid-template-columns:1fr}
  .core,.ruler{min-height:220px}
  .lim{grid-template-columns:1fr;gap:var(--s2)}
}
@media (max-width:860px){
  /* six stages will not fit a phone. Two rows of three keeps the sequence
     readable left-to-right rather than squeezing it into an unreadable strip. */
  .string{grid-template-columns:repeat(3,1fr)}
  .stg:nth-child(3){border-right:0}
  .stg:nth-child(-n+3){border-bottom:1px solid var(--hairline)}
}
@media (max-width:520px){
  body{padding:var(--s3) var(--s2)}
  .string{grid-template-columns:repeat(2,1fr)}
  .stg{border-right:1px solid var(--hairline)}
  .stg:nth-child(2n){border-right:0}
  .stg:nth-child(-n+4){border-bottom:1px solid var(--hairline)}
  .stg-n{font-size:17px}
  /* The form is one control per line rather than a row that does not fit. */
  form{display:flex;flex-wrap:wrap;gap:var(--s2)}
  input[type=text]{width:100%}
  button{width:100%}
  .funnel{grid-template-columns:1fr auto}
  .exhibit-head,.lim,.well{padding:var(--s2)}
}
@media (prefers-reduced-motion:reduce){
  *{transition:none !important;animation:none !important}
}
"""

JS = """
const RID = "__RID__";
const STRATA = ["#7A4A2E","#8A6440","#8E7A5C","#7E8478","#6E8A86"];
function bandFor(y){
  if(!y) return STRATA[2];
  if(y < 1990) return STRATA[0];
  if(y < 2000) return STRATA[1];
  if(y < 2010) return STRATA[2];
  if(y < 2020) return STRATA[3];
  return STRATA[4];
}
function n(x){ return (x===0||x) ? Number(x).toLocaleString() : "\\u2014"; }
function esc(s){ return String(s||"").replace(/[<>&]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;"}[c])); }

let painted = false;

async function tick(){
  const res = await fetch("/api/run/" + RID);
  if(!res.ok) return;
  const d = await res.json(), run = d.run;
  const total = run.candidates || 1;

  // A number is shown once the stage that produces it has produced something.
  // Before that it is a dash, not a zero: on a run that has not started reading,
  // "closest art 0" is a finding of none, which is a different and untrue claim.
  const reading = (run.screened || 0) > 0, over = run.status === "done";
  const yet = v => (reading || over) ? v : null;

  set("corpus", run.corpus_size); set("dropped", run.dropped_not_prior_art);
  set("family", run.dropped_same_family); set("eligible", run.eligible);
  set("screened", yet(run.screened)); set("closest", yet(run.closest));
  set("hot", yet(run.strong)); set("partial", yet(run.partial));

  // The drill string. A stage is "done" when its work finished and "live" when
  // it is the one currently cutting. Both are derived from run state, never from
  // a timer: if the run stalls, the rail stalls with it, which is the point.
  const nLim = (run.limitations||[]).length;
  const tasksDone = d.shards.filter(s => s.status === "done").length;
  const tasksTotal = d.shards.length || run.tasks || 0;
  //
  // Stage 4 is "the tasks are up", not "the tasks are finished", so that stage 5
  // is the live one while Gemini is actually reading. How many have finished is
  // the panel below; putting it here too made the rail stall on stage 4 for the
  // whole run, which is the part a person is watching.
  const stages = [
    { n: nLim,          done: nLim > 0 },
    { n: run.eligible,  done: run.eligible > 0 },
    { n: run.candidates,done: run.candidates > 0 },
    { n: tasksTotal || null, done: tasksTotal > 0 && d.shards.length >= tasksTotal },
    { n: yet(run.screened), done: over },
    { n: yet(run.closest),  done: over },
  ];
  // The live stage is the first one not yet finished.
  const liveAt = stages.findIndex(s => !s.done);
  stages.forEach((s, i) => {
    const el = document.getElementById("s" + (i+1));
    document.getElementById("n" + (i+1)).textContent = n(s.n);
    el.className = "stg" + (s.done ? " done" : (i === liveAt ? " live" : ""));
  });

  // Strata are painted once: the corpus does not change while a run is in flight.
  const core = document.getElementById("core");
  if(!painted && run.strata && run.strata.length){
    const slices = run.strata.length, h = 100 / slices;
    core.innerHTML = run.strata.map((s,i) =>
      `<div class="band" style="top:${(i*h).toFixed(3)}%;height:${(h+0.15).toFixed(3)}%;background:${bandFor(s.year)}"></div>`
    ).join("") + '<div class="drill" id="drill" style="height:0%"></div>';
    const ruler = document.getElementById("ruler");
    ruler.innerHTML = [0,.25,.5,.75,1].map(f =>
      `<div class="tick" style="top:calc(${(f*100).toFixed(0)}% - 6px)">${f===1?"":"\\u2500 "}${n(Math.round(f*total))}</div>`
    ).join("");
    painted = true;
  }

  const drill = document.getElementById("drill");
  if(drill) drill.style.height = Math.min(100, (run.screened/total)*100).toFixed(2) + "%";

  // Seams are cut at the depth a reference's rank actually occupies, and the
  // set drawn is capped.
  //
  // Two earlier versions failed here. Drawing all 231 flagged candidates, and
  // then all 45 that cleared the tier, both produced a barcode that hid the
  // strata completely. Seam density scales with candidate count, so this does
  // not resolve itself on a larger run; it gets worse. The column earns its
  // place only if a seam is rare, so the strongest references are drawn and the
  // count that was not drawn is stated in the caption rather than hidden.
  core.querySelectorAll(".seam").forEach(e => e.remove());
  const strong = (d.findings||[]).filter(f => (f.relevance||0) >= 3);
  const deepest = strong.reduce((a,f) => Math.max(a, f.rank||0), 0);
  const CAP = 12;
  const drawn = strong
    .slice()
    .sort((a,b) => (b.limitations_disclosed||[]).length - (a.limitations_disclosed||[]).length)
    .slice(0, CAP);
  if (deepest > 0 && !drawn.some(f => (f.rank||0) === deepest)) {
    drawn.push(strong.find(f => (f.rank||0) === deepest));
  }
  drawn.filter(Boolean).forEach(f => {
    const el = document.createElement("div");
    const lims = (f.limitations_disclosed||[]).length;
    el.className = "seam" + ((f.rank||0) === deepest && deepest > 0 ? " deepest" : "");
    el.style.top = Math.min(99.4, ((f.rank||0)/total)*100).toFixed(2) + "%";
    el.style.height = Math.max(2, Math.min(6, lims)) + "px";
    el.title = "US " + f.patent_id + " at depth " + n(f.rank) + ", " + lims + " limitations";
    core.appendChild(el);
  });
  const cap = document.getElementById("seamcap");
  if (cap) cap.textContent = strong.length > drawn.length
    ? drawn.length + " strongest of " + strong.length + " marked, thickness by limitations matched"
    : (strong.length ? strong.length + " marked, thickness by limitations matched" : "");

  feed(d.shards, run.findings || 0, tasksTotal);
  const note = document.getElementById("flownote");
  if(note) note.textContent = reduce
    ? "motion disabled by your system settings"
    : over
      ? "run complete, " + n(run.screened) + " candidates read across " +
        (d.shards.length || 0) + " tasks"
      : reading
        ? "one mark per four candidates read, one bright mark per finding"
        : tasksTotal
          ? tasksTotal + " lanes open, one per Cloud Run task. Nothing moves until a " +
            "task reports, so an empty face means the tasks are still starting"
          : "no task has reported yet";

  const done = d.shards.filter(s => s.status === "done").length;
  // Task marks are drawn from the moment the count is known, so ten empty marks
  // stand there waiting rather than nothing at all.
  const marks = d.shards.length ? d.shards.map(s =>
      `<div class="tk ${s.status==="done"?"done":"run"}" title="task ${s.index}: ${s.screened}/${s.assigned}"></div>`)
    : Array.from({length: tasksTotal}, (_, i) =>
      `<div class="tk" title="task ${i}: not reporting yet"></div>`);
  document.getElementById("tasks").innerHTML = marks.join("");

  // Elapsed matters more than any of it while nothing is happening: it is the
  // difference between a page that is waiting and a page that is broken.
  let el = "";
  if(run.launched_at && !over){
    const s = Math.max(0, Math.round(Date.now()/1000 - run.launched_at));
    el = " \\u00b7 " + (s < 90 ? s + "s" : Math.floor(s/60) + "m " + (s%60) + "s elapsed");
  }
  document.getElementById("status").textContent = (
    over ? done + " of " + (d.shards.length || tasksTotal) + " Cloud Run tasks finished"
    : d.shards.length === 0
      // What Cloud Run itself says, when it says anything. No promise about how
      // long: a job can sit queued for regional capacity, and a page that says
      // "within a minute" while the clock passes two is worse than one that says
      // plainly what state the execution is in.
      ? (run.exec_state || (tasksTotal
          ? "Cloud Run is starting " + tasksTotal + " tasks. Nothing reports until "
            + "a task is placed"
          : "waiting for Cloud Run to start the tasks"))
    : done === 0
      ? d.shards.length + " of " + tasksTotal + " tasks reading, none finished yet"
    : done + " of " + tasksTotal + " Cloud Run tasks finished") + el;

  document.getElementById("rows").innerHTML = (d.findings||[]).map(f =>
    `<tr><td class="n num">${n(f.rank)}</td>`+
    `<td class="n num">${(f.relevance||0)>=2
      ? `<a href="/chart/${RID}?ref=${esc(f.patent_id)}">US ${esc(f.patent_id)}</a>`
      : `US ${esc(f.patent_id)}`}</td>`+
    `<td class="n num">${esc((f.filing_date||"").slice(0,4))}</td>`+
    `<td><span class="tier ${(f.relevance||0)>=3?"hot":""}">${(f.relevance||0)>=3?"closest":((f.relevance||0)>=2?"worth reading":"partial")}</span></td>`+
    `<td class="n num">${n((f.limitations_disclosed||[]).length)}</td>`+
    `<td>${esc((f.summary||"").slice(0,150))}</td></tr>`
  ).join("");

  const chart = document.getElementById("chartlink");
  if(chart) chart.style.display = (run.strong > 0) ? "inline" : "none";
}
function set(id,v){ const e = document.getElementById(id); if(e) e.textContent = n(v); }

/* ------------------------------------------------------------------ *
 * The cut face.
 *
 * One lane per Cloud Run task. A particle is emitted for candidates that
 * were actually screened since the last poll, so the flow rate IS the
 * job's rate: when a shard stalls its lane goes quiet, and when the run
 * ends the canvas drains and the loop stops. Nothing is emitted on a
 * timer, because a flow that keeps flowing after the work stopped would
 * be a lie told in animation.
 *
 * Canvas rather than a 3D library: this is a 2D particle flow driven by
 * counts, and a WebGL dependency would be weight without benefit on a
 * page a judge loads once.
 * ------------------------------------------------------------------ */
const cv = document.getElementById("flow");
const cx = cv ? cv.getContext("2d") : null;
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
let parts = [], lanes = 1, prevScreened = {}, prevFound = 0, seen = 0, running = false;
const CSSVAR = k => getComputedStyle(document.body).getPropertyValue(k).trim();

function fit(){
  if(!cv) return;
  const r = cv.getBoundingClientRect(), d = devicePixelRatio || 1;
  cv.width = r.width * d; cv.height = r.height * d;
  cx.setTransform(d,0,0,d,0,0);
}
addEventListener("resize", () => { fit(); if(!running) rest(); });

/* Emission is derived from real progress, never invented. */
function feed(shards, findings, expected){
  if(!cv || reduce) return;
  const was = lanes;
  lanes = Math.max(1, shards.length || expected || 1);
  // Draw the lanes as soon as the task count is known. An empty ruled face says
  // ten tasks are about to cut here; an empty box says the page is broken.
  if(!running && (lanes !== was || !parts.length)) rest();
  shards.forEach(s => {
    const before = prevScreened[s.index] || 0;
    const delta  = Math.max(0, (s.screened || 0) - before);
    prevScreened[s.index] = s.screened || 0;
    // One particle per 4 candidates keeps a 2,000-candidate run legible
    // rather than a solid wall.
    for(let i = 0; i < Math.min(40, Math.ceil(delta / 4)); i++){
      parts.push({ lane: s.index % lanes, x: 0,
                   v: 0.55 + Math.random() * 0.75,
                   j: (Math.random() - 0.5) * 7, hit: false });
    }
  });
  const gained = Math.max(0, findings - prevFound);
  prevFound = findings;
  for(let i = 0; i < Math.min(18, gained); i++){
    parts.push({ lane: Math.floor(Math.random() * lanes), x: 0,
                 v: 0.5 + Math.random() * 0.4,
                 j: (Math.random() - 0.5) * 5, hit: true });
  }
  if(parts.length && !running){ running = true; requestAnimationFrame(draw); }
}

/* The lane rules on their own: the ground each task is cutting, with nothing
   moving through it yet. */
function rest(){
  if(!cv) return;
  const w = cv.clientWidth, h = cv.clientHeight, pad = 16;
  cx.clearRect(0,0,w,h);
  cx.strokeStyle = CSSVAR("--hairline") || "#3A413E"; cx.lineWidth = 1;
  for(let i = 0; i <= lanes; i++){
    const y = Math.round(pad + i*((h-pad*2)/lanes)) + .5;
    cx.beginPath(); cx.moveTo(pad, y); cx.lineTo(w-pad, y); cx.stroke();
  }
}

function draw(){
  if(!cv){ running = false; return; }
  const w = cv.clientWidth, h = cv.clientHeight;
  const ink3 = CSSVAR("--ink3") || "#6F7873";
  const seam = CSSVAR("--seam") || "#8CBF3F";
  const hair = CSSVAR("--hairline") || "#3A413E";
  cx.clearRect(0,0,w,h);

  // lane rules: the shards, drawn as the ground each task is cutting
  const pad = 16, laneH = (h - pad*2) / lanes;
  cx.strokeStyle = hair; cx.lineWidth = 1;
  for(let i = 0; i <= lanes; i++){
    const y = Math.round(pad + i*laneH) + .5;
    cx.beginPath(); cx.moveTo(pad, y); cx.lineTo(w - pad, y); cx.stroke();
  }

  let alive = 0;
  for(const p of parts){
    p.x += p.v;
    if(p.x > w - pad*2){ continue; }
    alive++;
    const y = pad + p.lane*laneH + laneH/2 + p.j;
    if(p.hit){
      cx.fillStyle = seam;
      cx.fillRect(pad + p.x - 3, y - 1.5, 6, 3);
    } else {
      cx.globalAlpha = .5;
      cx.fillStyle = ink3;
      cx.fillRect(pad + p.x, y - 1, 2, 2);
      cx.globalAlpha = 1;
    }
  }
  parts = parts.filter(p => p.x <= w - pad*2);

  if(alive){ requestAnimationFrame(draw); }
  else { running = false; rest(); }
}

fit();
tick(); setInterval(tick, 2000);
"""


def head(title: str, sub: str) -> str:
    """Everything down to the open body tag.

    Split out of `shell` so a slow page can be written to the browser in pieces
    rather than held back until the work behind it finishes.
    """
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        f"<title>{title}</title>"
        f'<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel=stylesheet href="{FONTS}">'
        f"<style>{CSS}</style></head><body>"
        '<header><div class=mark><b>NIGHTSHIFT</b> '
        "<span>&#183; prior-art core log</span></div>"
        f"<div class=sub>{sub}</div></header>"
    )


def shell(title: str, sub: str, body: str, script: str = "") -> HTMLResponse:
    return HTMLResponse(
        head(title, sub)
        + body
        + (f"<script>{script}</script>" if script else "")
        + "</body></html>"
    )


def _run_budget_note() -> str:
    """Say up front what a press of the button will and will not do.

    A button that refuses is only honest if it says so before it is pressed
    rather than after.
    """
    if DAILY_RUN_CAP > 0:
        return ""
    return (
        "<div class=note style='margin-top:14px;border-top:1px solid var(--hairline);"
        "padding-top:14px'>"
        "A patent already searched below opens its finished run straight away. "
        "Starting a <em>new</em> search reads 2,000 patents with Gemini for about "
        "$34, and this public deployment will not spend that, so it refuses and "
        "explains rather than pretending the button is not there. Reading a letter "
        "still works; it costs about a cent."
        "</div>"
    )


@app.get("/", response_class=HTMLResponse)
def index():
    rows = "".join(
        f"<tr><td class='n num'><a href='/run/{r.get('run_id','')}'>"
        f"{r.get('run_id','')}</a></td>"
        f"<td>{(r.get('title') or '')[:52]}</td>"
        f"<td class='n num'>{r.get('candidates',0):,}</td>"
        f"<td class=n>{r.get('status','')}</td></tr>"
        for r in store.recent_runs(10)
    )
    table = (
        "<div class=scroller><table>"
        "<tr><th>run</th><th>patent</th><th>read</th><th>state</th></tr>"
        f"{rows}</table></div>"
        if rows
        else "<div class=note>No runs yet.</div>"
    )

    return shell(
        "Nightshift",
        "A patent demand letter takes a professional search and weeks to answer. "
        "Nightshift ranks 171,695 patents, reads the closest 2,000 against every "
        "claim limitation, and hands your attorney the answer.",
        f"""
<div class=well>
  <form method=post action=/run>
    <input type=text name=patent placeholder="Asserted patent number" required
           aria-label="Asserted patent number">
    <button type=submit>Sink a borehole</button>
  </form>
  <form method=post action=/read-letter enctype=multipart/form-data class=drop>
    <span>Or hand it the letter and let Gemini find the number</span>
    <input type=file name=letter accept="application/pdf,image/*" required
           aria-label="Demand letter, PDF or photo">
    <button type=submit>Read the letter</button>
  </form>
  <div class=note>
    Every US patent in CPC G06Q that predates this patent's priority date is
    ranked, and Gemini reads the top {DEFAULT_CANDIDATES:,} of them against every
    limitation of claim 1. The work runs across {DEFAULT_TASKS} Cloud Run tasks.
    Close the tab; the run continues without you.
  </div>
  {_run_budget_note()}
</div>
<div class=well><h2>Recent boreholes</h2>{table}</div>
<div class=caveat>
  Prior-art evidence dossier, not a legal opinion. Nightshift reports what a
  reference discloses. It does not decide whether a claim is invalid, and its
  output is prepared for review by licensed patent counsel.
</div>
<div class=note><a href=/eval>How accurate is it, and measured against what</a></div>
""",
    )


@app.post("/read-letter", response_class=HTMLResponse)
async def read_letter(letter: UploadFile = File(...)):
    """Take the letter itself and find the asserted patent in it.

    The first step of this job was always manual: a person reads the letter,
    finds the number, strips the commas, types it in. Gemini reads the document
    directly, so a phone photograph of a page works the same as a PDF.
    """
    raw = await letter.read()
    if not raw:
        return _refused("That file was empty.", "Try the PDF or a photo of the letter.")
    if len(raw) > 12 * 1024 * 1024:
        return _refused(
            "That file is too large.",
            "Twelve megabytes is the limit. A photo of the page is plenty.",
        )

    allowed, _ = store.claim_daily_run(DAILY_LETTER_CAP, kind="letter")
    if not allowed:
        return _refused(
            "Not reading another letter today.",
            "Reading a document is a Gemini vision call, and this deployment caps "
            "how many it will make in a day. Try tomorrow, or enter the patent "
            "number directly.",
        )

    mime = letter.content_type or "application/pdf"
    try:
        found = judge.read_demand_letter(raw, mime)
    except Exception as exc:  # noqa: BLE001
        return _refused("Could not read that file.", _esc(str(exc)[:180]))

    patents = [p for p in found.get("patents", []) if p.get("number")]
    if not found.get("is_assertion") or not patents:
        return _refused(
            "No asserted patent found in that document.",
            "Nightshift looks for a US patent number the sender is asserting "
            "against you. If you know the number, enter it directly.",
        )

    sender = _esc(found.get("sender") or "the sender")
    rows = "".join(
        f"<tr><td class='n num'>US {_esc(p['number'])}</td>"
        f"<td>{_esc(p.get('context',''))[:150]}</td>"
        f"<td><form method=post action=/run style='display:inline'>"
        f"<input type=hidden name=patent value='{_esc(p['number'])}'>"
        f"<button type=submit>Search this one</button></form></td></tr>"
        for p in patents[:6]
    )

    return shell(
        "Nightshift",
        "Read from the letter by Gemini",
        f"""
<div class=well>
  <h2>Asserted against you</h2>
  <div class=note style="margin-bottom:14px">
    Gemini read the document you uploaded and found
    {"this patent" if len(patents) == 1 else f"these {len(patents)} patents"}
    being asserted by {sender}. Nothing was typed in.
  </div>
  <div class=scroller><table>
    <tr><th>patent</th><th>where it appears in the letter</th><th></th></tr>
    {rows}
  </table></div>
</div>
<div class=note><a href="/">Enter a number instead</a></div>
""",
    )


@app.post("/run")
def start(patent: str = Form(...), force: int = Form(0)):
    """Start a run, or explain in a sentence why it cannot start.

    Everything that can be known to be impossible is decided here, before a
    Cloud Run Job is launched. A patent with no claim text or outside the corpus
    produces a page, not a stack trace, and not a billed run that cannot find
    anything.

    Two things also stop a run that is merely wasteful. A patent already searched
    to this depth is answered from the finished run, because paying thirty-four
    dollars and waiting four minutes to reproduce an answer that exists helps
    nobody. And
    the number of runs this service will start in a day is capped, because it is
    public, unauthenticated, and its main button spends money.
    """
    pid = "".join(ch for ch in patent if ch.isdigit())
    if not pid:
        return _refused(
            f"&ldquo;{_esc(patent[:60])}&rdquo; is not a patent number.",
            "Enter the number from the demand letter, digits only. "
            "For example 10140422.",
        )

    if not force:
        prior = store.completed_run_for(pid, DEFAULT_CANDIDATES)
        if prior:
            return _already_searched(pid, prior)

    if DAILY_RUN_CAP <= 0:
        return _refused(
            f"US {_esc(pid)} has not been searched, and this deployment will not "
            "start a new one.",
            "Reading 2,000 patents against every limitation of a claim costs about "
            "thirty-four dollars of Gemini, and the hackathon credit that paid for "
            "the runs on this site is spent. Rather than take the button away, it "
            "refuses and says why. Everything already searched is open: the runs on "
            "the home page, their claim charts, the accuracy page, and the letter "
            "intake, which reads a real demand letter with Gemini and costs about a "
            "cent.<br><br>To run this patent yourself against your own project, the "
            "repository is at "
            "<a href='https://github.com/JonathanSolvesProblems/nightshift'>"
            "github.com/JonathanSolvesProblems/nightshift</a> and the command is "
            f"<code>python -m priorart.orchestrate {_esc(pid)}</code>.",
        )

    allowed, used = store.claim_daily_run(DAILY_RUN_CAP)
    if not allowed:
        return _refused(
            "Not starting another search today.",
            f"This service starts at most {DAILY_RUN_CAP} new searches a day, and "
            f"{used} have run. Each one reads 2,000 patents with Gemini and costs "
            "about thirty-four dollars, so the ceiling is a real one rather than a "
            "throttle. The finished runs on the home page are open to read.",
        )

    return StreamingResponse(
        _sink(pid),
        media_type="text/html; charset=utf-8",
        # Nothing between here and the browser may hold the body back: the whole
        # point is that each line arrives when it happens.
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def _sink(pid: str):
    """Write the preparation of a run out to the browser as it happens.

    Preparing a run is about a minute of BigQuery and Gemini before the core log
    exists to redirect to: the claim split, the retrieval scan, the funnel counts
    and the depth strata. Holding the response for that minute is indistinguishable
    from a hung page, and the first thing anyone does with a hung page is press the
    button again, which bills a second run.

    So the response opens immediately and each stage is appended as it lands. The
    numbers on screen are the real ones coming back from the work, which means the
    wait is also the first thing that shows the machine is doing something.
    """
    yield head(f"Sinking US {_esc(pid)}",
               "Preparing the run. Nothing is billed to a task yet.")
    yield ("<div class=well><h2>Sinking a borehole against "
           f"US&nbsp;{_esc(pid)}</h2><ol class=steps>")
    run_id = ""
    try:
        for kind, text in orchestrate.prepare_iter(pid, DEFAULT_CANDIDATES):
            if kind == "done":
                run_id = text
                break
            yield f"<li class={'fact' if kind == 'fact' else 'step'}>{_esc(text)}</li>"
        else:
            raise RuntimeError("preparation finished without producing a run")
    except (LookupError, ValueError, RuntimeError) as exc:
        yield ("</ol></div>"
               + _refusal(f"Cannot search against US {_esc(pid)}.", _esc(str(exc)))
               + "</body></html>")
        return

    # Launched in the request rather than a background thread. Cloud Run throttles
    # CPU once a response is finished, so a thread outliving its request is a race;
    # the job launch is one API call and shows here as a stage like any other.
    yield f"<li class=step>launching {DEFAULT_TASKS} Cloud Run tasks</li>"
    try:
        orchestrate.launch(run_id, DEFAULT_TASKS)
    except Exception as exc:  # noqa: BLE001
        yield ("</ol></div>"
               + _refusal("The run was prepared but the tasks did not launch.",
                          _esc(str(exc)[:200]))
               + "</body></html>")
        return

    yield (f"<li class=fact>run {_esc(run_id)}</li></ol>"
           f'<div class=note style="margin-top:16px">'
           f'<a href="/run/{run_id}">Open the core log</a></div></div>'
           f'<script>location.replace("/run/{run_id}")</script></body></html>')


def _already_searched(pid: str, prior: dict) -> HTMLResponse:
    """Hand back the finished run rather than paying to reproduce it."""
    when = time.strftime("%Y-%m-%d %H:%M UTC",
                         time.gmtime(prior.get("created_at") or 0))
    rid = _esc(prior.get("run_id", ""))
    return shell(
        "Already searched",
        f"US {_esc(pid)} &#183; {_esc(prior.get('title',''))}",
        f"""
<div class=well>
  <h2>This one has been searched</h2>
  <div class=note style="margin-bottom:14px">
    US&nbsp;{_esc(pid)} was searched on {when}: {prior.get('candidates',0):,}
    candidates read against every limitation of claim 1. That run is finished and
    open to read.
  </div>
  <div class=note><a href="/run/{rid}">Open the core log</a></div>
  <div class=note style="margin-top:18px">
    Searching it again reads the same 2,000 patents with Gemini, takes about four
    minutes, and costs about thirty-four dollars. It is the same corpus and the same
    claim, so it will find the same art.
  </div>
  <form method=post action=/run style="margin-top:14px">
    <input type=hidden name=patent value="{_esc(pid)}">
    <input type=hidden name=force value="1">
    <button type=submit>Search it again anyway</button>
  </form>
  <div class=note style="margin-top:16px"><a href="/">Search a different patent</a></div>
</div>
""",
    )


def _refusal(headline: str, detail: str) -> str:
    return f"""
<div class=well>
  <div style="font-size:17px;margin-bottom:10px">{headline}</div>
  <div class=note>{detail}</div>
  <div class=note style="margin-top:16px"><a href="/">Try another number</a></div>
</div>
"""


def _refused(headline: str, detail: str) -> HTMLResponse:
    return shell(
        "Nightshift",
        "Prior-art evidence for a patent demand letter",
        _refusal(headline, detail),
    )


_EXEC_CACHE: dict[str, tuple[float, str]] = {}


def _execution_state(name: str) -> str:
    """One sentence on what Cloud Run says about an execution that is not reporting.

    Until a task writes its first shard there is nothing in Firestore to show, and
    a job queued behind regional capacity looks exactly like a job that failed to
    launch: ten empty task marks and a page that appears stuck. Cloud Run knows
    which it is, so it is worth one call to ask, cached because the page polls
    every two seconds and this does not change that fast.
    """
    now = time.time()
    hit = _EXEC_CACHE.get(name)
    if hit and now - hit[0] < 10:
        return hit[1]

    phrase = ""
    try:
        ex = run_v2.ExecutionsClient().get_execution(name=name)
        total = ex.task_count or 0
        if ex.running_count:
            phrase = (f"{ex.running_count} of {total} tasks running on Cloud Run, "
                      "none has reported in yet")
        else:
            waiting = any(c.type_ == "Retry" for c in ex.conditions)
            phrase = (
                f"Cloud Run has the execution queued and is waiting for capacity "
                f"to place {total} tasks"
                if waiting else
                next((c.message for c in ex.conditions
                      if c.type_ == "Started" and c.state != c.State.CONDITION_SUCCEEDED),
                     "")
            )
    except Exception:  # noqa: BLE001
        phrase = ""

    _EXEC_CACHE[name] = (now, phrase)
    return phrase


@app.get("/api/run/{run_id}")
def api_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        return JSONResponse({"error": "not found"}, status_code=404)
    shards = store.list_shards(run_id)
    if not shards and run.get("execution") and run.get("status") != "done":
        run["exec_state"] = _execution_state(run["execution"])
    all_findings = store.list_findings(run_id)
    run["screened"] = sum(s.get("screened", 0) for s in shards)
    run["findings"] = len(all_findings)
    # Two tiers, counted over the whole run and truncated only for display.
    # Screening is deliberately generous because it decides what gets read
    # closely, so the raw flagged count overstates what is worth an attorney's
    # time. Relevance 2+ addresses part of the claimed approach; 1 is same field.
    # Three tiers, because the retrieval upgrade made the top one meaningful.
    #
    # On the 64-dimensional prefilter, relevance 3 was vanishingly rare and the
    # useful line sat at 2. With gemini-embedding-001 the candidate window is
    # dense enough that 552 of 1,375 screened clear relevance 2, which is not a
    # shortlist anybody can work from, while 39 clear relevance 3. The tier that
    # matters moved, so the reporting moved with it rather than continuing to
    # headline a number that had stopped being useful.
    run["closest"] = sum(1 for f in all_findings if (f.get("relevance") or 0) >= 3)
    run["strong"] = sum(1 for f in all_findings if (f.get("relevance") or 0) == 2)
    run["partial"] = run["findings"] - run["closest"] - run["strong"]
    return JSONResponse({"run": run, "shards": shards, "findings": all_findings[:80]})


@app.get("/run/{run_id}", response_class=HTMLResponse)
def run_page(run_id: str):
    run = store.get_run(run_id)
    if not run:
        return shell("Not found", run_id, "<div class=well>No such borehole.</div>")

    return shell(
        f"US {run.get('target')} core log",
        f"US {run.get('target')} &#183; {run.get('title','')} &#183; "
        f"priority {run.get('priority_date','')}",
        """
<div class=well>
  <h2>The run</h2>
  <div class=string id=string>
    <div class=stg id=s1><div class="stg-n num" id=n1>&mdash;</div>
      <div class=stg-l>claim 1 split<br>by Gemini</div></div>
    <div class=stg id=s2><div class="stg-n num" id=n2>&mdash;</div>
      <div class=stg-l>eligible on<br>priority date</div></div>
    <div class=stg id=s3><div class="stg-n num" id=n3>&mdash;</div>
      <div class=stg-l>ranked by<br>embedding</div></div>
    <div class=stg id=s4><div class="stg-n num" id=n4>&mdash;</div>
      <div class=stg-l>Cloud Run<br>tasks</div></div>
    <div class=stg id=s5><div class="stg-n num" id=n5>&mdash;</div>
      <div class=stg-l>read against<br>every limitation</div></div>
    <div class=stg id=s6><div class="stg-n num" id=n6>&mdash;</div>
      <div class=stg-l>closest<br>art</div></div>
  </div>
</div>

<div class=well>
  <div class=rig>
    <div>
      <h2>Depth</h2>
      <div class=corewrap>
        <div class=core id=core></div>
        <div class=ruler id=ruler></div>
      </div>
      <div class=note id=seamcap style="font-size:11px;max-width:none"></div>
    </div>
    <div>
      <h2>Cut</h2>
      <dl class=funnel>
        <dt>in CPC G06Q</dt><dd class=num id=corpus>&mdash;</dd>
        <div></div><div></div>
        <dt class=minus>filed after the priority date</dt>
        <dd class="num minus" id=dropped>&mdash;</dd>
        <dt class=minus>same disclosure family</dt>
        <dd class="num minus" id=family>&mdash;</dd>
        <dt class=keep>eligible as prior art</dt><dd class="num keep" id=eligible>&mdash;</dd>
        <dt>read by Gemini</dt><dd class=num id=screened>&mdash;</dd>
        <dt class=found>closest art</dt><dd class="num found" id=closest>&mdash;</dd>
        <dt>worth reading</dt><dd class=num id=hot>&mdash;</dd>
        <dt>partial overlap</dt><dd class=num id=partial>&mdash;</dd>
      </dl>
      <div class=lip>
        <h2>The cut face</h2>
        <div class=flowwrap>
          <canvas id=flow></canvas>
          <div class=flowlab>eligible corpus</div>
          <div class="flowlab r">closest art</div>
        </div>
        <div class=note id=flownote style="font-size:11px"></div>
      </div>
      <div class=lip>
        <h2>Cloud Run tasks</h2>
        <div class=tasks id=tasks></div>
        <div class=note id=status>reading the run</div>
        <div class=note><a id=chartlink href="/chart/__RID__" style="display:none">
        Draw the claim chart for the deepest strong reference</a></div>
      </div>
    </div>
  </div>
</div>
<div class=well>
  <h2>Seams</h2>
  <div class=scroller><table><thead><tr><th>depth</th><th>reference</th><th>filed</th><th>tier</th>
  <th>lims</th><th>what it discloses</th></tr></thead>
  <tbody id=rows></tbody></table></div>
</div>
""".replace("__RID__", run_id),
        JS.replace("__RID__", run_id),
    )


@app.get("/chart/{run_id}", response_class=HTMLResponse)
def chart_page(run_id: str, ref: str | None = None):
    """The deliverable: one reference mapped limitation by limitation.

    `ref` charts a specific reference rather than the top-ranked one, because
    which reference is worth charting is the user's call: the strongest match on
    the screen's own ranking is not always the one an attorney wants mapped.

    Charting is computed on demand and cached per reference, because it reads far
    more text per reference than screening does and only makes sense for
    references screening actually surfaced.
    """
    run = store.get_run(run_id)
    if not run:
        return shell("Not found", run_id, "<div class=well>No such borehole.</div>")

    charts = run.get("charts") or {}
    cached = charts.get(ref) if ref else run.get("chart")
    if not cached:
        findings = [f for f in store.list_findings(run_id) if (f.get("relevance") or 0) >= 2]
        if ref:
            findings = [f for f in findings if str(f.get("patent_id")) == str(ref)]
        if not findings:
            return shell(
                "No chart yet",
                run_id,
                "<div class=well><div class=note>No reference has cleared the "
                "'worth reading' tier yet. The chart is drawn from those only.</div></div>",
            )
        target = findings[0]
        limitations = [
            judge.Limitation(index=l["index"], text=l["text"])
            for l in run.get("limitations", [])
        ]
        cand = _candidate_for(run_id, target["patent_id"])
        mappings = judge.chart(cand, limitations, judge.client())
        cached = {
            "patent_id": target["patent_id"],
            "title": target.get("title", ""),
            "filing_date": target.get("filing_date", ""),
            "rank": target.get("rank", 0),
            "mappings": [
                {
                    "limitation": m.limitation,
                    "level": m.level,
                    "mapped_text": m.mapped_text,
                    "reasoning": m.reasoning,
                }
                for m in mappings
            ],
        }
        if ref:
            charts[str(ref)] = cached
            store.update_run(run_id, charts=charts)
        else:
            store.update_run(run_id, chart=cached)

    lim_text = {l["index"]: l["text"] for l in run.get("limitations", [])}
    labels = {
        "FULL": ("taught by this reference", ""),
        "PARTIAL": ("substance taught, wording narrower", "partial"),
        "ABSENT": ("not taught by this reference", "absent"),
    }
    rows = ""
    for m in cached["mappings"]:
        lid = m["limitation"]
        level = (m.get("level") or ("FULL" if m.get("discloses") else "ABSENT")).upper()
        caption, cls = labels.get(level, labels["ABSENT"])
        quote = (
            f'<div class="quote {cls}">{_esc(m["mapped_text"])}</div>'
            if m.get("mapped_text")
            else f'<div class="quote {cls}">No supporting passage in this reference.</div>'
        )
        rows += (
            f'<div class=lim><div><div class=lim-id>{_esc(lid)}</div>'
            f'<div class=lim-text>{_esc(lim_text.get(lid, ""))}</div></div>'
            f'<div><div class="level {cls}">{caption}</div>{quote}'
            f'<div class=why>{_esc(m["reasoning"])}</div></div></div>'
        )

    def _lvl(m):
        return (m.get("level") or ("FULL" if m.get("discloses") else "ABSENT")).upper()

    full = sum(1 for m in cached["mappings"] if _lvl(m) == "FULL")
    partial = sum(1 for m in cached["mappings"] if _lvl(m) == "PARTIAL")
    total = len(cached["mappings"])

    return shell(
        f"Claim chart US {cached['patent_id']}",
        f"US {run.get('target')} claim 1, mapped against US {cached['patent_id']}",
        f"""
<div class=exhibit>
  <div class=exhibit-head>
    <h2>Prior-art evidence dossier</h2>
    <div style="font-size:19px;margin-bottom:6px">US {cached['patent_id']}
      &#183; <span class=num>{_esc(str(cached.get('filing_date',''))[:10])}</span></div>
    <div class=lim-text>{_esc(cached.get('title',''))}</div>
    <div class=note>
      Surfaced at depth <span class=num>{cached.get('rank',0):,}</span> of
      <span class=num>{run.get('eligible',0):,}</span> eligible references.
      Of <span class=num>{total}</span> limitations,
      <span class=num>{full}</span> {"is" if full == 1 else "are"} taught by this
      reference and <span class=num>{partial}</span>
      {"is" if partial == 1 else "are"} taught in substance with narrower claim
      wording.
    </div>
  </div>
  {rows}
</div>
<div class=caveat>
  Not a legal opinion and not a validity determination. Each row states what this
  reference discloses, quoted from the reference itself. Whether the asserted
  claim is invalid is a question for licensed patent counsel and, ultimately, for
  a court or the Patent Trial and Appeal Board.
</div>
<div class=note><a href="/run/{run_id}">Back to the core log</a></div>
""",
    )


def _candidate_for(run_id: str, patent_id: str):
    """Re-read one candidate's disclosure from the run's own table."""
    from dataclasses import dataclass

    from google.cloud import bigquery

    from . import config

    @dataclass
    class C:
        patent_id: str
        title: str
        filing_date: str
        disclosure: str

    client = bigquery.Client(project=config.PROJECT_ID, location=config.LOCATION)
    sql = f"""
    SELECT patent_id, title, filing_date, disclosure
    FROM `{config.working_table(f"run_{run_id}")}`
    WHERE patent_id = @pid
    """
    rows = list(
        client.query(
            sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("pid", "STRING", patent_id)
                ]
            ),
        ).result()
    )
    r = rows[0]
    return C(r["patent_id"], r["title"] or "", str(r["filing_date"]), r["disclosure"] or "")


def _esc(s) -> str:
    return (
        str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


@app.get("/eval", response_class=HTMLResponse)
def eval_page():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "eval", "screening.json")
    try:
        with open(os.path.abspath(path), encoding="utf-8") as fh:
            data = json.load(fh)
        label = {
            "X": "examiner applied it to anticipate (&sect;102)",
            "Y": "examiner applied it for obviousness (&sect;103)",
            "CONTROL": "examiner never cited it",
        }
        rows = "".join(
            f"<tr><td>{label[c]}</td><td class='n num'>{data['by_category'][c]['n']}</td>"
            f"<td class='n num'>{data['by_category'][c]['found_rate']}%</td></tr>"
            for c in ("X", "Y", "CONTROL")
            if c in data["by_category"]
        )
        table = (
            "<table><tr><th>reference set</th><th>n</th><th>found</th></tr>"
            f"{rows}</table>"
        )
    except FileNotFoundError:
        table = "<div class=note>eval/screening.json is not present in this image.</div>"

    return shell(
        "Accuracy",
        "Graded against references USPTO examiners actually applied in rejections",
        f"""
<div class=well><h2>Blinded screening accuracy</h2>{table}
<div class=note>
  The model never saw the reference's patent number, title, assignee or dates, so
  it could not lean on anything it may have memorised. The control row is what
  makes the other two mean anything: recall alone is trivially gained by flagging
  everything, so the same screener was run over references the examiner did not
  cite, drawn from the same corpus and passing the same priority-date gate.
</div></div>
<div class=well><h2>Scope, stated in full</h2>
<div class=note>
  The denominator is examiner-applied references that are granted US patents
  inside the 171,695-patent corpus. 73% of examiner citations point at pre-grant
  publications and 6% at non-patent literature; both sit outside this corpus and
  are excluded from numerator and denominator alike.
</div>
<div class=note>
  This is recall against the examiner, not against ground truth. An examiner's
  own search runs 45 to 85% recall, so every reference Nightshift finds that the
  examiner missed is scored here as a miss. The number is a floor, not an
  estimate.
</div></div>
<div class=note><a href="/">Back</a></div>
""",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
