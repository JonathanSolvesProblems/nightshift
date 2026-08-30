"""The judgment stage: Gemini reads candidate references and decides.

This is the part that is not retrieval. Every surviving candidate is actually
read against the asserted claim, rather than ranked and handed to a human.

Two passes, because reading every candidate against every limitation is wasteful
when most candidates are irrelevant to all of them:

    screen  one call per candidate, all limitations at once, cheap verdict
    chart   survivors only, per-limitation mapping with the supporting span

Output discipline, which is deliberate and not decoration. Nightshift reports
what a reference DISCLOSES. It never states that a claim is invalid. Validity is
decided by a court or the PTAB, and an automated tool asserting it would be both
wrong about its own competence and useless to the attorney who has to file.
"""

from __future__ import annotations

import concurrent.futures
import os
import re
import time
from dataclasses import dataclass, field

from google import genai
from google.genai import types

MODEL = os.environ.get("PRIOR_ART_MODEL", "gemini-3.5-flash")
MAX_WORKERS = int(os.environ.get("PRIOR_ART_WORKERS", "16"))

# Screening reads abstract plus claims. Enough to decide relevance, small enough
# to keep a wide fan-out affordable.
SCREEN_CHARS = 14000


@dataclass
class Limitation:
    index: str          # "1(a)"
    text: str


@dataclass
class Mapping:
    limitation: str
    mapped_text: str
    reasoning: str
    level: str = "ABSENT"      # FULL | PARTIAL | ABSENT
    discloses: bool = False    # FULL or PARTIAL


@dataclass
class Verdict:
    patent_id: str
    title: str
    filing_date: str
    relevant: bool = False
    relevance: int = 0
    limitations_disclosed: list[str] = field(default_factory=list)
    summary: str = ""
    mappings: list[Mapping] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0


def client() -> genai.Client:
    """Vertex AI by default, AI Studio only as an explicit fallback.

    The AI Studio free tier caps some models at 20 requests per day, which is not
    a rate limit you can back off around when the unit of work is thousands of
    candidates. Vertex AI runs against the billed project and is what the whole
    fan-out actually depends on.
    """
    if os.environ.get("PRIOR_ART_USE_AI_STUDIO"):
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        return genai.Client(api_key=key)

    return genai.Client(
        vertexai=True,
        project=os.environ.get("PRIOR_ART_PROJECT", "prior-art-agent-2026"),
        location=os.environ.get("PRIOR_ART_VERTEX_LOCATION", "global"),
    )


def _cfg(schema: dict) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        response_schema=schema,
    )


_RETRYABLE = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "INTERNAL")


def generate(gc: genai.Client, prompt: str, schema: dict, attempts: int = 6):
    """Call Gemini with backoff.

    A screening pass over thousands of candidates will hit transient 503s and
    rate limits as a matter of course, so retries are part of the unit of work
    rather than something bolted on around it.

    Retries stay on the SAME model deliberately. An earlier version escalated
    through a fallback chain on each attempt and promptly exhausted a sibling
    model's 20-requests-per-day free-tier quota, converting a recoverable
    overload into a hard stop.
    """
    delay = 2.0
    last: Exception | None = None

    for attempt in range(attempts):
        try:
            return gc.models.generate_content(
                model=MODEL, contents=prompt, config=_cfg(schema)
            )
        except Exception as exc:  # noqa: BLE001 - classify by message, not type
            last = exc
            if not any(tok in str(exc) for tok in _RETRYABLE):
                raise
            if attempt == attempts - 1:
                break
            # Deterministic jitter from the attempt index; no global RNG state.
            time.sleep(delay + (attempt % 3) * 0.5)
            delay = min(delay * 2, 32.0)

    raise RuntimeError(f"gemini unavailable after {attempts} attempts: {last}")


# ---------------------------------------------------------------------------
# Claim decomposition
# ---------------------------------------------------------------------------

SPLIT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "limitations": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "index": {"type": "STRING"},
                    "text": {"type": "STRING"},
                },
                "required": ["index", "text"],
            },
        }
    },
    "required": ["limitations"],
}


def split_claim(claim_text: str, gc: genai.Client | None = None) -> list[Limitation]:
    """Break a claim into the limitations a chart has one row per.

    A claim chart is scored limitation by limitation, so this decomposition
    determines the shape of everything downstream.
    """
    gc = gc or client()
    prompt = (
        "Break this patent claim into its individual limitations, the way a "
        "patent attorney would when building a claim chart.\n\n"
        "Keep the preamble as limitation 1(pre). Label the rest 1(a), 1(b), and "
        "so on. Use the claim's own wording verbatim for each limitation; do not "
        "paraphrase or summarize.\n\n"
        f"CLAIM:\n{claim_text}"
    )
    resp = generate(gc, prompt, SPLIT_SCHEMA)
    data = resp.parsed or {}
    return [
        Limitation(index=l["index"], text=l["text"])
        for l in data.get("limitations", [])
    ]


# ---------------------------------------------------------------------------
# Pass 1: screening
# ---------------------------------------------------------------------------

SCREEN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "relevance": {"type": "INTEGER"},
        "limitations_addressed": {"type": "ARRAY", "items": {"type": "STRING"}},
        "summary": {"type": "STRING"},
    },
    "required": ["relevance", "limitations_addressed", "summary"],
}

# Screening scores MATERIALITY, not anticipation, and the distinction is not
# cosmetic.
#
# An examiner's rejection applies to the claims as they stood at that office
# action. The applicant then amends to overcome it, so the ISSUED claim is by
# construction the version that survived the reference. Asking "does this
# reference anticipate the issued claim" of a reference the examiner actually
# applied is close to guaranteed to return no, which is exactly what the first
# run did: zero hits on a known category-X pair.
#
# So screening asks the question a searcher actually asks, which is whether this
# reference is worth an attorney's attention. Limitation-by-limitation mapping is
# real work, but it belongs in the chart stage where the output is evidence
# rather than a filter.
RELEVANCE_SCALE = """0  unrelated subject matter
1  same general field, but does not address the claimed approach
2  addresses part of the claimed approach; some limitations have a counterpart
3  addresses substantially the whole claimed approach"""


def screen(
    candidate,
    limitations: list[Limitation],
    gc: genai.Client,
    blind: bool = True,
) -> Verdict:
    """Decide whether one reference is worth charting.

    `blind` strips the reference's identity from the prompt. The model is asked
    to reason from disclosure text alone, so it cannot lean on anything it might
    have memorized about a well-known patent number. The blinded arm is the one
    reported in ACCURACY.md.
    """
    lim_block = "\n".join(f"[{l.index}] {l.text}" for l in limitations)
    header = "" if blind else f"Reference: US {candidate.patent_id}, {candidate.title}\n"

    prompt = (
        "You are a patent searcher triaging prior art. Decide whether this "
        "reference is material enough that an attorney building an invalidity "
        "position should read it.\n\n"
        "Judge the technical substance, not the wording. Prior art almost never "
        "uses the claim's vocabulary, so a reference that describes the same "
        "mechanism in different words still counts. Generic implementation "
        "boilerplate (processors, memory, non-transitory storage media, network "
        "connections) is not what distinguishes the claim; do not withhold "
        "relevance because such recitations are absent.\n\n"
        f"RELEVANCE SCALE:\n{RELEVANCE_SCALE}\n\n"
        f"CLAIM LIMITATIONS:\n{lim_block}\n\n"
        f"REFERENCE TEXT:\n{header}{candidate.disclosure[:SCREEN_CHARS]}\n\n"
        "List the labels of limitations that have a counterpart in the "
        "reference, even a partial one. State no conclusion about validity."
    )

    resp = generate(gc, prompt, SCREEN_SCHEMA)
    data = resp.parsed or {}
    usage = resp.usage_metadata

    score = int(data.get("relevance", 0) or 0)
    addressed = [normalize_label(x) for x in data.get("limitations_addressed", [])]

    # Promote on evidence, not on the model's self-rating alone.
    #
    # The 0-3 scale is a judgment call and references sit right on the 1/2
    # boundary, so the same reference scored 2 and then 1 across runs while
    # consistently identifying the same three limitations. Thresholding the
    # integer alone made the filter flap; the list of limitations it actually
    # found a counterpart for is the more stable signal.
    #
    # Screening is also allowed to be generous. It decides what gets read
    # closely, and the chart stage does the strict limitation-by-limitation
    # work, so a false positive here costs one more call while a false negative
    # loses the reference for good.
    relevant = score >= 2 or len(addressed) >= 2

    return Verdict(
        patent_id=candidate.patent_id,
        title=candidate.title,
        filing_date=candidate.filing_date,
        relevance=score,
        relevant=relevant,
        limitations_disclosed=addressed,
        summary=data.get("summary", ""),
        tokens_in=getattr(usage, "prompt_token_count", 0) or 0,
        # Billed output is the answer plus the thinking that produced it.
        #
        # `candidates_token_count` is only the visible JSON. Gemini 3.5 Flash
        # thinks by default and reports those tokens separately, but Vertex bills
        # them at the output rate, and on this prompt they run about five times
        # the visible answer. Counting only the visible half understated the cost
        # of a run by roughly two and a half times, which was not discovered in
        # the code but in a billing alert.
        tokens_out=((getattr(usage, "candidates_token_count", 0) or 0)
                    + (getattr(usage, "thoughts_token_count", 0) or 0)),
    )


def screen_all(
    candidates,
    limitations: list[Limitation],
    blind: bool = True,
    workers: int = MAX_WORKERS,
    on_result=None,
) -> list[Verdict]:
    """Fan out screening across candidates.

    Local threads here; the deployed version distributes the same unit of work
    across Cloud Run Jobs. The unit is deliberately identical so the
    two paths cannot drift.
    """
    gc = client()
    out: list[Verdict] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(screen, c, limitations, gc, blind): c for c in candidates
        }
        for fut in concurrent.futures.as_completed(futures):
            try:
                v = fut.result()
            except Exception as exc:  # one bad candidate must not kill the run
                cand = futures[fut]
                v = Verdict(
                    patent_id=cand.patent_id,
                    title=cand.title,
                    filing_date=cand.filing_date,
                    relevant=False,
                    summary=f"screening failed: {type(exc).__name__}",
                )
            out.append(v)
            if on_result:
                on_result(v)
    return out


# ---------------------------------------------------------------------------
# Pass 2: charting
# ---------------------------------------------------------------------------

CHART_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "mappings": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "limitation": {"type": "STRING"},
                    "level": {"type": "STRING", "enum": ["FULL", "PARTIAL", "ABSENT"]},
                    "mapped_text": {"type": "STRING"},
                    "reasoning": {"type": "STRING"},
                },
                "required": ["limitation", "level", "mapped_text", "reasoning"],
            },
        }
    },
    "required": ["mappings"],
}

# Charting takes three states, not two.
#
# A binary discloses/does-not collapses the most common real case, which is a
# reference that teaches the substance of a limitation while omitting a piece of
# claim boilerplate. The first version of this prompt returned ABSENT for all
# eight limitations of a reference screening had matched on all eight, because it
# withheld on wording like "non-volatile" and "mobile application". An all-absent
# chart is not a careful chart, it is a useless one, and it disagreed with the
# stage that selected the reference in the first place.
CHART_LEVELS = """FULL     the reference teaches this limitation, including its substantive requirements
PARTIAL  the reference teaches the substance but omits or generalises part of it
ABSENT   the reference does not teach this limitation at all"""


def chart(candidate, limitations: list[Limitation], gc: genai.Client) -> list[Mapping]:
    """Build the per-limitation mapping for one reference.

    `mapped_text` must be copied verbatim from the reference so the attorney can
    find it, and so an empty span is a visible signal that nothing was found.
    """
    lim_block = "\n".join(f"[{l.index}] {l.text}" for l in limitations)
    valid = ", ".join(l.index for l in limitations)
    prompt = (
        "Build a claim chart row for every limitation below against this "
        "reference.\n\n"
        "Return the limitation LABEL only in the `limitation` field, exactly as "
        f"given. Valid labels are: {valid}. Do not put the limitation text there.\n\n"
        "Judge technical substance, not wording. Prior art rarely uses the "
        "claim's vocabulary, so a reference teaching the same mechanism in "
        "different words still counts. Generic implementation recitations "
        "(processors, memory, non-transitory or non-volatile storage, mobile "
        "devices, network connections) are not what distinguishes a claim; do not "
        "return ABSENT because such wording is missing when the substance is "
        "present. Use PARTIAL for that case.\n\n"
        f"LEVELS:\n{CHART_LEVELS}\n\n"
        "Quote the exact span of the reference that supports your finding, copied "
        "verbatim, for FULL and PARTIAL. Leave mapped_text empty for ABSENT. "
        "Never invent text that is not in the reference, and never state a "
        "conclusion about validity.\n\n"
        f"CLAIM LIMITATIONS:\n{lim_block}\n\n"
        f"REFERENCE TEXT:\n{candidate.disclosure[:20000]}"
    )
    resp = generate(gc, prompt, CHART_SCHEMA)
    data = resp.parsed or {}

    # The label is matched leniently. An earlier version trusted it verbatim, and
    # when the model returned the whole limitation text instead of the label the
    # lookup silently returned nothing and the chart rendered the claim text in
    # the label's style, unreadable.
    by_norm = {normalize_label(l.index): l.index for l in limitations}

    out: list[Mapping] = []
    for m in data.get("mappings", []):
        raw = m.get("limitation", "")
        key = normalize_label(raw)
        label = by_norm.get(key)
        if label is None:
            label = next(
                (idx for norm, idx in by_norm.items() if key.startswith(norm)), raw
            )
        level = (m.get("level") or "ABSENT").upper()
        out.append(
            Mapping(
                limitation=label,
                level=level,
                discloses=level in ("FULL", "PARTIAL"),
                mapped_text=m.get("mapped_text", ""),
                reasoning=m.get("reasoning", ""),
            )
        )
    return out


def normalize_label(s: str) -> str:
    """Limitation labels come back with inconsistent spacing and case."""
    return re.sub(r"\s+", "", s).lower()


# ---------------------------------------------------------------------------
# Reading the letter
# ---------------------------------------------------------------------------

LETTER_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "patents": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "number": {"type": "STRING"},
                    "context": {"type": "STRING"},
                },
                "required": ["number", "context"],
            },
        },
        "sender": {"type": "STRING"},
        "is_assertion": {"type": "BOOLEAN"},
    },
    "required": ["patents", "sender", "is_assertion"],
}


def read_demand_letter(data: bytes, mime_type: str, gc: genai.Client | None = None) -> dict:
    """Pull the asserted patent numbers out of a letter, PDF or photograph.

    This is the actual first step of the job. Somebody receives a letter, and
    before anything can happen a human has to find the patent number in it,
    strip the commas, and type it somewhere. That is small, and it is also the
    only part of this whole process that was still manual.

    Gemini reads the document directly: no OCR step, no parsing rules, and a
    phone photograph of a page works the same as a PDF.

    Returns the patent numbers found, who sent it, and whether the document
    actually asserts a patent at all, because the honest answer to a holiday
    photo is "this is not a demand letter" rather than a guess.
    """
    gc = gc or client()
    prompt = (
        "This document may be a patent demand or assertion letter.\n\n"
        "Find every US patent being asserted against the recipient. Report each "
        "number as digits only, with no commas and no 'US' prefix, and give a "
        "short quote showing where it appears.\n\n"
        "Do not report patents that are merely mentioned as background, owned by "
        "the recipient, or listed in a signature block or letterhead. Only "
        "patents the sender is asserting.\n\n"
        "If this is not a patent assertion at all, set is_assertion false and "
        "return an empty list. Do not guess a number that is not there."
    )
    resp = gc.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=data, mime_type=mime_type),
            prompt,
        ],
        config=_cfg(LETTER_SCHEMA),
    )
    data_out = resp.parsed or {}
    for p in data_out.get("patents", []):
        p["number"] = "".join(ch for ch in str(p.get("number", "")) if ch.isdigit())
    return data_out
