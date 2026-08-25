"""Capture the demo surfaces at 1280x720, including the specific claim chart.

    python scripts/shoot_demo.py <run_id> <reference_patent_id>
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "https://nightshift-1015687974010.us-central1.run.app"
OUT = Path("docs/shots")


def main() -> int:
    run_id, ref = sys.argv[1], sys.argv[2]
    pages = [
        ("demo-run", f"/run/{run_id}"),
        ("demo-chart", f"/chart/{run_id}?ref={ref}"),
    ]
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
                page.goto(BASE + path, wait_until="networkidle", timeout=180_000)
                page.wait_for_timeout(4000)
                out = OUT / f"{name}-{scheme}.png"
                page.screenshot(path=str(out))
                print(f"  {out}")
            ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
