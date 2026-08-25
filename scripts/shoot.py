"""Screenshot the live surfaces at the size a judge actually sees them.

The design audit's screenshot test is run at 1280x720, the frame of a demo video
and a typical browser, not at full monitor width. A layout that only works at
1800px wide has failed the test that matters.

    python scripts/shoot.py <run_id>
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://nightshift-1015687974010.us-central1.run.app"
OUT = Path("docs/shots")


def main() -> int:
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    pages = [("home", "/"), ("eval", "/eval")]
    if run_id:
        pages += [("run", f"/run/{run_id}"), ("chart", f"/chart/{run_id}")]

    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for scheme in ("dark", "light"):
            ctx = browser.new_context(
                viewport={"width": 1280, "height": 720},
                device_scale_factor=2,
                color_scheme=scheme,
            )
            page = ctx.new_page()
            for name, path in pages:
                page.goto(BASE + path, wait_until="networkidle", timeout=90_000)
                # The run page paints from a poll, so give it one cycle.
                page.wait_for_timeout(3500 if name in ("run", "chart") else 1200)
                out = OUT / f"{name}-{scheme}.png"
                page.screenshot(path=str(out))
                print(f"  {out}")
            ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
