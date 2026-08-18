"""Prove the Gemini path works on a real prior-art screening judgment.

This is the core operation of the whole agent: given one claim limitation and one
candidate reference, decide whether the reference discloses the limitation. If
this does not work well, nothing downstream matters.
"""

import json
import os
import sys
import urllib.request

MODEL = os.environ.get("PRIOR_ART_MODEL", "gemini-3.5-flash")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

# Real text. Claim 1 of US 7,240,025 "Internet advertising system and method",
# reduced to one limitation, against a plainly relevant hypothetical reference.
LIMITATION = (
    "a first interface to the computer system through which each of the internet "
    "media venues is prompted to input presentation rules for the internet media "
    "venue for displaying electronic advertisements on the internet media venue"
)

REFERENCE = (
    "The publisher console allows each participating web site operator to define "
    "display constraints for advertisements shown on that site, including permitted "
    "banner dimensions, prohibited content categories, and maximum animation length. "
    "These constraints are stored per-publisher and enforced by the ad server at "
    "serving time."
)

PROMPT = f"""You are screening prior art for patent invalidity analysis.

CLAIM LIMITATION under examination:
{LIMITATION}

CANDIDATE REFERENCE passage:
{REFERENCE}

Decide whether the reference discloses this limitation. Answer strictly as JSON:
{{"discloses": true|false, "confidence": 0.0-1.0, "mapped_text": "the exact span of the reference that meets the limitation, or empty", "reasoning": "one sentence"}}"""


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY not set", file=sys.stderr)
        return 1

    # A response schema is the difference between "usually valid JSON" and
    # "always valid JSON". At 10,000 candidates per run, a 1% parse failure rate
    # is 100 dropped judgments, so the schema is not optional.
    schema = {
        "type": "OBJECT",
        "properties": {
            "discloses": {"type": "BOOLEAN"},
            "confidence": {"type": "NUMBER"},
            "mapped_text": {"type": "STRING"},
            "reasoning": {"type": "STRING"},
        },
        "required": ["discloses", "confidence", "mapped_text", "reasoning"],
    }

    body = json.dumps(
        {
            "contents": [{"parts": [{"text": PROMPT}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
    ).encode()

    req = urllib.request.Request(
        ENDPOINT.format(m=MODEL),
        data=body,
        headers={"Content-Type": "application/json", "X-goog-api-key": key},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.load(resp)

    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    usage = payload.get("usageMetadata", {})

    print(f"model   {MODEL}")
    print(f"tokens  in={usage.get('promptTokenCount')} out={usage.get('candidatesTokenCount')}")
    print("verdict:")
    print(json.dumps(json.loads(text), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
