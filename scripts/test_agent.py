"""Exercise the ADK intake agent against a real completed run.

    python scripts/test_agent.py <run_id>
"""

import asyncio
import sys

from google.genai import types

sys.path.insert(0, "src")

from google.adk.runners import InMemoryRunner  # noqa: E402

from priorart.agent import root_agent  # noqa: E402

QUESTIONS = [
    "how far along is run {rid}?",
    "for run {rid}, what are the two references most worth reading?",
    "in run {rid}, which references address limitation 1(a)?",
    "so is the patent in run {rid} invalid?",
]


async def main() -> int:
    rid = sys.argv[1]
    runner = InMemoryRunner(agent=root_agent, app_name="nightshift")
    session = await runner.session_service.create_session(
        app_name="nightshift", user_id="tester"
    )

    for q in QUESTIONS:
        text = q.format(rid=rid)
        print(f"\n>>> {text}")
        async for event in runner.run_async(
            user_id="tester",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=text)]),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if getattr(part, "function_call", None):
                        print(f"    [tool] {part.function_call.name}")
                    elif getattr(part, "text", None):
                        print(f"    {part.text.strip()[:600]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
