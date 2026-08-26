"""Interface invariants: contrast, reduced motion, narrow viewport, keyboard.

These are correctness, not taste. A design that reads well at 1280x720 in one
theme and fails WCAG contrast in the other, or animates through
prefers-reduced-motion, is broken regardless of how it looks.

    python scripts/audit_ui.py <run_id>
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = "https://nightshift-1015687974010.us-central1.run.app"

# Token pairs that must clear WCAG AA. Values come from .design/manifest.json.
PAIRS = {
    "dark": [
        ("ink on field", "#E8EAE6", "#262B29", 4.5),
        ("ink2 on field", "#A8AFA9", "#262B29", 4.5),
        ("ink3 on well", "#6F7873", "#1D2220", 3.0),
        ("seam on field", "#8CBF3F", "#262B29", 3.0),
        ("seam-ink on seam", "#1A1F18", "#8CBF3F", 4.5),
    ],
    "light": [
        ("ink on field", "#1F2422", "#D8DBD5", 4.5),
        ("ink2 on field", "#4C5451", "#D8DBD5", 4.5),
        ("ink3 on well", "#565E5A", "#C6CAC3", 3.0),
        ("seam on field", "#4F7318", "#D8DBD5", 3.0),
        ("accent-ink on seam", "#F2F5EE", "#4F7318", 4.5),
    ],
}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def _lin(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexstr: str) -> float:
    h = hexstr.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def ratio(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def audit_contrast() -> None:
    for theme, pairs in PAIRS.items():
        for name, fg, bg, need in pairs:
            r = ratio(fg, bg)
            check(f"{theme}: {name} >= {need}:1", r >= need, f"{r:.2f}:1")


def audit_browser(run_id: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # Reduced motion: no transition may remain on the animated elements.
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720}, reduced_motion="reduce"
        )
        page = ctx.new_page()
        page.goto(f"{BASE}/run/{run_id}", wait_until="networkidle", timeout=120_000)
        page.wait_for_timeout(3000)
        moving = page.evaluate(
            """() => [...document.querySelectorAll('.seam,.drill')]
                 .filter(e => {
                   const t = getComputedStyle(e).transitionDuration;
                   return t && t !== '0s' && !t.startsWith('0s');
                 }).length"""
        )
        check("prefers-reduced-motion disables seam/drill transitions", moving == 0,
              f"{moving} still animating")
        ctx.close()

        # Narrow viewport: no horizontal overflow.
        ctx = browser.new_context(viewport={"width": 390, "height": 780})
        page = ctx.new_page()
        for name, path in (("home", "/"), ("run", f"/run/{run_id}")):
            page.goto(BASE + path, wait_until="networkidle", timeout=120_000)
            page.wait_for_timeout(2500)
            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            check(f"390px {name}: no horizontal scroll", overflow <= 1, f"{overflow}px")
        ctx.close()

        # Keyboard: the primary control must be reachable and focusable.
        ctx = browser.new_context(viewport={"width": 1280, "height": 720})
        page = ctx.new_page()
        page.goto(BASE + "/", wait_until="networkidle", timeout=120_000)
        page.keyboard.press("Tab")
        for _ in range(6):
            tag = page.evaluate("() => document.activeElement.tagName")
            if tag == "INPUT":
                break
            page.keyboard.press("Tab")
        check("keyboard reaches the patent input",
              page.evaluate("() => document.activeElement.tagName") == "INPUT")
        page.keyboard.press("Tab")
        check("and then the submit control",
              page.evaluate("() => document.activeElement.tagName") == "BUTTON")

        # The page must carry a language and a title.
        check("html has lang", page.evaluate("() => document.documentElement.lang") != "")
        check("page has a title", len(page.title()) > 0, page.title())
        ctx.close()
        browser.close()


def main() -> int:
    run_id = sys.argv[1]
    print("interface invariants\n")
    audit_contrast()
    audit_browser(run_id)
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    for name, _, detail in failed:
        print(f"  FAILED: {name}  {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
