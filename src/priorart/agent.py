"""ADK intake agent: the conversational surface over a completed borehole.

Scope is deliberate. The fan-out is NOT routed through ADK. Screening thousands
of candidates is a batch job that Cloud Run Jobs already shards correctly, and
forcing that through an agent loop would be visible contortion for no gain.

What ADK is genuinely good at, and what it does here, is the part either side of
the batch: take a patent number in natural language, start the work, and then let
someone interrogate the result afterwards without reading a JSON blob.

    "run the numbers on 10140422"
    "which references teach limitation 1(c)?"
    "how deep was the examiner's reference?"

Every tool below reads state the pipeline actually produced. The agent has no
ability to invent a finding: it can only look one up.
"""

from __future__ import annotations

import os

from google.adk.agents import Agent

from . import orchestrate, store

MODEL = os.environ.get("PRIOR_ART_AGENT_MODEL", "gemini-3.5-flash")
BASE_URL = os.environ.get(
    "PRIOR_ART_BASE_URL", "https://nightshift-1015687974010.us-central1.run.app"
)


def start_search(patent_number: str, candidates: int = 2000) -> dict:
    """Start a prior-art search against an asserted patent.

    Use this when someone gives you a patent number they have been accused of
    infringing, or asks to search for prior art against one.

    Args:
        patent_number: The US patent number, digits only, for example "10140422".
        candidates: How many ranked candidates to read. More is deeper and slower.

    Returns:
        The run id and where to watch it.
    """
    pid = "".join(ch for ch in str(patent_number) if ch.isdigit())
    if not pid:
        return {"status": "error", "detail": "No patent number found in that input."}
    try:
        run_id = orchestrate.prepare(pid, candidates)
        orchestrate.launch(run_id, int(os.environ.get("PRIOR_ART_TASKS", "10")))
    except LookupError:
        return {
            "status": "error",
            "detail": f"US {pid} is not in the CPC G06Q corpus, which is the "
            "class this build covers.",
        }
    return {
        "status": "started",
        "run_id": run_id,
        "watch": f"{BASE_URL}/run/{run_id}",
        "note": "This runs in the background across Cloud Run tasks. It does not "
        "need the caller to stay connected.",
    }


def get_progress(run_id: str) -> dict:
    """Report how far a running prior-art search has got.

    Args:
        run_id: The run id returned by start_search.
    """
    run = store.get_run(run_id)
    if not run:
        return {"status": "error", "detail": f"No run {run_id}."}
    shards = store.list_shards(run_id)
    findings = store.list_findings(run_id)
    strong = [f for f in findings if (f.get("relevance") or 0) >= 2]
    return {
        "status": run.get("status"),
        "target": run.get("target"),
        "title": run.get("title"),
        "eligible_prior_art": run.get("eligible"),
        "dropped_not_prior_art": run.get("dropped_not_prior_art"),
        "screened": sum(s.get("screened", 0) for s in shards),
        "tasks_finished": len([s for s in shards if s.get("status") == "done"]),
        "tasks_total": len(shards),
        "worth_reading": len(strong),
        "partial_overlap": len(findings) - len(strong),
    }


def top_references(run_id: str, limit: int = 5) -> dict:
    """List the references most worth an attorney's time, deepest detail first.

    Args:
        run_id: The run id.
        limit: How many references to return.
    """
    findings = [
        f for f in store.list_findings(run_id) if (f.get("relevance") or 0) >= 2
    ]
    if not findings:
        return {"status": "empty", "detail": "Nothing has cleared the tier yet."}
    return {
        "status": "ok",
        "references": [
            {
                "patent": f"US {f.get('patent_id')}",
                "filed": str(f.get("filing_date", ""))[:10],
                "found_at_depth": f.get("rank"),
                "limitations_matched": len(f.get("limitations_disclosed") or []),
                "what_it_discloses": f.get("summary", ""),
                "claim_chart": f"{BASE_URL}/chart/{run_id}?ref={f.get('patent_id')}",
            }
            for f in findings[:limit]
        ],
    }


def explain_limitation(run_id: str, limitation: str) -> dict:
    """Say which references address one specific limitation of claim 1.

    Args:
        run_id: The run id.
        limitation: The limitation label, for example "1(c)" or "1(pre)".
    """
    want = limitation.strip().lower().replace(" ", "")
    findings = store.list_findings(run_id)
    hits = [
        {
            "patent": f"US {f.get('patent_id')}",
            "found_at_depth": f.get("rank"),
            "what_it_discloses": f.get("summary", ""),
        }
        for f in findings
        if any(
            str(x).strip().lower().replace(" ", "") == want
            for x in (f.get("limitations_disclosed") or [])
        )
    ]
    return {
        "status": "ok",
        "limitation": limitation,
        "matching_references": len(hits),
        "references": hits[:8],
    }


INSTRUCTION = """
You are the intake desk for Nightshift, a prior-art search that runs overnight.

Someone talking to you has usually just received a patent demand letter and is
frightened by it. Be brief, concrete and calm. Do not perform sympathy.

What you can do:
  - start a search from a patent number
  - report progress on a running search
  - list the references worth reading, and link their claim charts
  - say which references address a particular limitation

Two things you must never do.

Never state or imply that a patent is invalid, that a claim is anticipated, or
that someone has a good case. Nightshift reports what a reference discloses.
Validity is decided by a court or the Patent Trial and Appeal Board, and the
output is evidence prepared for review by licensed patent counsel. If asked
whether the patent is invalid, say plainly that you cannot answer that, and point
at the claim chart as the thing their attorney will want.

Never describe a reference you have not looked up with a tool. If a tool returns
nothing, say so. An invented citation in this domain is worse than no answer.

When a search is running, say that it continues without the caller and give them
the link.
"""

root_agent = Agent(
    name="nightshift_intake",
    model=MODEL,
    description=(
        "Starts and reports on prior-art searches against an asserted patent, "
        "and explains which references address which claim limitations."
    ),
    instruction=INSTRUCTION,
    tools=[start_search, get_progress, top_references, explain_limitation],
)
