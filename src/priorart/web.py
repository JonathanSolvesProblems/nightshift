"""Cloud Run service: start runs and watch them.

Three routes, because a background job needs exactly three things from a UI:
somewhere to start it, somewhere to watch it, and somewhere to read the result.

    /              start a run, list recent ones
    /run/{id}      live funnel, worker grid, findings as they land
    /eval          the accuracy table, with its denominator stated
"""

from __future__ import annotations

import json
import os
import threading

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from . import orchestrate, store

app = FastAPI(title="Nightshift")

DEFAULT_TASKS = int(os.environ.get("PRIOR_ART_TASKS", "10"))
DEFAULT_CANDIDATES = int(os.environ.get("PRIOR_ART_CANDIDATES", "2000"))

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0b0d10;color:#e6e9ef;font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;padding:34px 26px;max-width:1080px;margin:0 auto}
a{color:#7fb2ff;text-decoration:none}
h1{font-size:19px;letter-spacing:.14em;text-transform:uppercase;font-weight:600}
h1 span{color:#5b6472}
.sub{color:#8b95a5;font-size:13px;margin-top:6px}
.card{background:#12151a;border:1px solid #1e232b;border-radius:9px;padding:18px;margin-top:18px}
.funnel{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px}
.stat{background:#0e1116;border:1px solid #1e232b;border-radius:7px;padding:13px}
.stat .n{font:600 25px/1.1 ui-monospace,SFMono-Regular,Menlo,monospace;color:#e6e9ef}
.stat .l{color:#7d879a;font-size:11px;text-transform:uppercase;letter-spacing:.09em;margin-top:6px}
.stat.drop .n{color:#e08a5a}
.stat.hit .n{color:#5ad1a0}
.grid{display:flex;flex-wrap:wrap;gap:5px;margin-top:12px}
.t{width:26px;height:26px;border-radius:4px;background:#1a1f27;border:1px solid #232935;font:600 10px/24px ui-monospace,monospace;text-align:center;color:#5b6472}
.t.run{background:#1d3a5c;border-color:#2f5f96;color:#9dc8ff}
.t.done{background:#1d4437;border-color:#2c6b53;color:#7fe3bb}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;color:#7d879a;font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding:8px 10px;border-bottom:1px solid #1e232b}
td{padding:9px 10px;border-bottom:1px solid #161a20;vertical-align:top}
td.mono{font-family:ui-monospace,monospace;color:#9dc8ff;white-space:nowrap}
input,button{font:inherit}
input[type=text]{background:#0e1116;border:1px solid #262c36;color:#e6e9ef;border-radius:7px;padding:11px 13px;width:230px}
button{background:#2f6bd8;border:0;color:#fff;border-radius:7px;padding:11px 20px;font-weight:600;cursor:pointer}
.note{color:#7d879a;font-size:12.5px;margin-top:10px;line-height:1.6}
.warn{background:#1a1410;border:1px solid #3d2a18;color:#d8a878;border-radius:7px;padding:11px 13px;font-size:12.5px;margin-top:16px}
.pill{display:inline-block;background:#1a1f27;border:1px solid #262c36;border-radius:20px;padding:2px 10px;font-size:11px;color:#8b95a5}
"""

SHELL = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head><body>
<h1>NIGHT<span>SHIFT</span></h1>
<div class=sub>{sub}</div>
{body}</body></html>"""


def page(title: str, sub: str, body: str) -> HTMLResponse:
    return HTMLResponse(SHELL.format(title=title, css=CSS, sub=sub, body=body))


@app.get("/", response_class=HTMLResponse)
def index():
    rows = ""
    for r in store.recent_runs(12):
        rid = r.get("run_id", "")
        rows += (
            f"<tr><td class=mono><a href='/run/{rid}'>{rid}</a></td>"
            f"<td>{(r.get('title') or '')[:58]}</td>"
            f"<td class=mono>{r.get('status','')}</td>"
            f"<td class=mono>{r.get('findings',0)}</td></tr>"
        )
    table = (
        f"<table><tr><th>run</th><th>patent</th><th>status</th><th>findings</th></tr>{rows}</table>"
        if rows
        else "<div class=note>No runs yet.</div>"
    )

    return page(
        "Nightshift",
        "Prior-art evidence for a patent demand letter",
        f"""
<div class=card>
  <form method=post action=/run>
    <input type=text name=patent placeholder="Patent number, e.g. 10002398" required>
    <button type=submit>Run overnight</button>
  </form>
  <div class=note>
    Nightshift ranks every US patent in CPC G06Q that predates this patent's
    priority date, then has Gemini read the top {DEFAULT_CANDIDATES:,} of them
    against each limitation of claim 1. It runs as a background job across
    {DEFAULT_TASKS} Cloud Run tasks. Close the tab; the run continues.
  </div>
</div>
<div class=card><h1 style="font-size:13px">Recent runs</h1><div style="margin-top:12px">{table}</div></div>
<div class=warn>Prior-art evidence dossier, not a legal opinion. Nightshift reports
what a reference discloses. It does not decide whether a claim is invalid.
Prepared for review by licensed patent counsel.</div>
<div class=note><a href=/eval>Accuracy and how it was measured</a></div>
""",
    )


@app.post("/run")
def start(patent: str = Form(...)):
    pid = "".join(ch for ch in patent if ch.isdigit())
    run_id = orchestrate.prepare(pid, DEFAULT_CANDIDATES)
    # Launch off the request thread so the browser is not held open waiting on
    # the Cloud Run Jobs API.
    threading.Thread(
        target=orchestrate.launch, args=(run_id, DEFAULT_TASKS), daemon=True
    ).start()
    return RedirectResponse(f"/run/{run_id}", status_code=303)


@app.get("/api/run/{run_id}")
def api_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        return JSONResponse({"error": "not found"}, status_code=404)
    shards = store.list_shards(run_id)
    findings = store.list_findings(run_id, 60)
    run["screened"] = sum(s.get("screened", 0) for s in shards)
    run["findings"] = len(findings)
    return JSONResponse({"run": run, "shards": shards, "findings": findings})


@app.get("/run/{run_id}", response_class=HTMLResponse)
def run_page(run_id: str, request: Request):
    run = store.get_run(run_id)
    if not run:
        return page("Not found", run_id, "<div class=card>No such run.</div>")

    return page(
        f"Run {run_id}",
        f"US {run.get('target')} &mdash; {run.get('title','')}",
        f"""
<div class=card>
  <div class=funnel>
    <div class=stat><div class=n id=corpus>0</div><div class=l>corpus</div></div>
    <div class="stat drop"><div class=n id=dropped>0</div><div class=l>not prior art</div></div>
    <div class=stat><div class=n id=eligible>0</div><div class=l>eligible</div></div>
    <div class=stat><div class=n id=screened>0</div><div class=l>read by Gemini</div></div>
    <div class="stat hit"><div class=n id=found>0</div><div class=l>material</div></div>
  </div>
  <div class=grid id=grid></div>
  <div class=note id=status>starting</div>
</div>
<div class=card>
  <h1 style="font-size:13px">Findings</h1>
  <div style="margin-top:12px"><table id=ft>
    <tr><th>patent</th><th>filed</th><th>limitations</th><th>what it discloses</th></tr>
  </table></div>
</div>
<script>
const rid={run_id!r};
function n(x){{return (x||0).toLocaleString()}}
async function tick(){{
  const r = await fetch('/api/run/'+rid); if(!r.ok) return;
  const d = await r.json(); const run=d.run;
  corpus.textContent=n(run.corpus_size);
  dropped.textContent=n(run.dropped_not_prior_art);
  eligible.textContent=n(run.eligible);
  screened.textContent=n(run.screened);
  found.textContent=n(run.findings);
  grid.innerHTML = d.shards.map(s=>
    `<div class="t ${{s.status==='done'?'done':'run'}}" title="${{s.screened}}/${{s.assigned}}">${{s.index}}</div>`).join('');
  const done=d.shards.filter(s=>s.status==='done').length;
  status.textContent = run.status==='queued' ? 'queued'
    : `${{done}} of ${{d.shards.length||run.tasks||0}} Cloud Run tasks finished`;
  ft.innerHTML = '<tr><th>patent</th><th>filed</th><th>limitations</th><th>what it discloses</th></tr>' +
    d.findings.map(f=>`<tr><td class=mono>US ${{f.patent_id}}</td><td class=mono>${{(f.filing_date||'').slice(0,10)}}</td>`+
    `<td><span class=pill>${{(f.limitations_disclosed||[]).length}}</span></td>`+
    `<td>${{(f.summary||'').slice(0,190)}}</td></tr>`).join('');
}}
tick(); setInterval(tick, 2000);
</script>
""",
    )


@app.get("/eval", response_class=HTMLResponse)
def eval_page():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "eval", "screening.json")
    try:
        with open(os.path.abspath(path), encoding="utf-8") as fh:
            data = json.load(fh)
        rows = ""
        label = {
            "X": "X &mdash; examiner applied as anticipation (&sect;102)",
            "Y": "Y &mdash; examiner applied as obviousness (&sect;103)",
            "CONTROL": "control &mdash; never cited by the examiner",
        }
        for cat in ("X", "Y", "CONTROL"):
            v = data["by_category"].get(cat)
            if v:
                rows += (
                    f"<tr><td>{label[cat]}</td><td class=mono>{v['n']}</td>"
                    f"<td class=mono>{v['found_rate']}%</td></tr>"
                )
        table = f"<table><tr><th>set</th><th>n</th><th>flagged</th></tr>{rows}</table>"
    except FileNotFoundError:
        table = "<div class=note>eval/screening.json not present in this image.</div>"

    return page(
        "Accuracy",
        "Graded against references USPTO examiners actually applied",
        f"""
<div class=card>{table}
<div class=note>
Blinded: the model never saw the reference's patent number, title, assignee or
dates. The control is the number that makes the other two mean anything, since
recall alone is trivially gained by flagging everything. Controls are drawn from
the same corpus and the same CPC class and pass the same priority-date gate.
</div></div>
<div class=card><div class=note>
<b>Scope, stated in full.</b> The denominator is examiner-applied references that
are granted US patents inside the 171,695-patent corpus. 73% of examiner
citations point at pre-grant publications and 6% at non-patent literature; both
are outside this corpus and excluded from numerator and denominator alike.
This is recall against the examiner, not against ground truth: an examiner's own
search runs 45 to 85% recall, so every reference Nightshift finds that the
examiner missed is scored here as a miss. The number is a floor.
</div></div>
<div class=note><a href="/">Back</a></div>
""",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
