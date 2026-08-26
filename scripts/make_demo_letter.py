"""Render the demo demand letter, and check Gemini reads it.

The letter is a prop and says so. The sender is a fictional entity and the
recipient is a fictional company, because putting a real firm's name on a
fabricated legal threat would be wrong regardless of how clearly it is labelled.

The patent it asserts is real, and it is the demo target, so the extraction step
is a genuine read of a genuine number rather than a lookup of something planted.

    python scripts/make_demo_letter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, "src")

OUT = Path("docs/demo")

LETTER = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;600&display=swap');
  body{margin:0;background:#fff;font:15px/1.65 "Source Serif 4",Georgia,serif;color:#12110f}
  .page{width:816px;min-height:1056px;padding:78px 86px;box-sizing:border-box}
  .lh{border-bottom:2px solid #12110f;padding-bottom:14px;margin-bottom:34px}
  .lh h1{font-size:19px;letter-spacing:.16em;text-transform:uppercase;margin:0}
  .lh div{font-size:11.5px;color:#666;margin-top:5px;letter-spacing:.04em}
  .meta{font-size:13px;color:#444;margin-bottom:30px;line-height:1.8}
  p{margin:0 0 15px}
  .re{font-weight:600;margin-bottom:22px}
  .pat{font-weight:600}
  .sig{margin-top:40px;font-size:13.5px;line-height:1.8}
  .prop{position:absolute;top:14px;right:16px;font:11px/1 ui-sans-serif,sans-serif;
        color:#b00;border:1px solid #b00;padding:5px 9px;letter-spacing:.1em}
</style>
<div class=prop>FICTIONAL &middot; DEMO PROP</div>
<div class=page>
  <div class=lh>
    <h1>Merrow &amp; Vance Holdings LLC</h1>
    <div>Intellectual Property Licensing &middot; 1400 Ashcroft Plaza, Suite 900</div>
  </div>

  <div class=meta>
    26 August 2026<br>
    Ms. Priya Raghunathan, Chief Executive<br>
    Halverson Retail Systems, Inc.
  </div>

  <div class=re>Re: Notice of infringement and offer of license</div>

  <p>We write on behalf of Merrow &amp; Vance Holdings LLC, owner by assignment
  of a portfolio of patents concerning consumer loyalty and point-of-sale
  transaction systems.</p>

  <p>It has come to our attention that Halverson Retail Systems operates a
  customer rewards platform which, in our assessment, practises one or more
  claims of <span class=pat>United States Patent No. 10,163,121</span>,
  entitled "System and method for targeted marketing and consumer resource
  management." We direct your attention in particular to claim 1.</p>

  <p>Our client is prepared to resolve this matter through a paid-up licence.
  We would ask that you respond within thirty (30) days of the date of this
  letter, after which our client reserves all rights and remedies available to
  it, including the commencement of proceedings.</p>

  <p>This letter is written without prejudice to our client's rights, all of
  which are expressly reserved.</p>

  <div class=sig>
    Yours faithfully,<br><br>
    <strong>D. Merrow</strong><br>
    Director of Licensing<br>
    Merrow &amp; Vance Holdings LLC
  </div>
</div>
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / "demand-letter.png"
    pdf = OUT / "demand-letter.pdf"

    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_context(viewport={"width": 816, "height": 1056},
                             device_scale_factor=2).new_page()
        page.set_content(LETTER, wait_until="networkidle")
        page.wait_for_timeout(900)
        page.screenshot(path=str(png), full_page=True)
        page.pdf(path=str(pdf), width="8.5in", height="11in", print_background=True)
        b.close()

    print(f"  {png}")
    print(f"  {pdf}")

    # Now the real check: does Gemini find the number without being told it?
    from priorart import judge

    for path, mime in ((png, "image/png"), (pdf, "application/pdf")):
        found = judge.read_demand_letter(path.read_bytes(), mime)
        nums = [p.get("number") for p in found.get("patents", [])]
        ok = "10163121" in nums
        print(f"\n  {path.suffix[1:].upper()}: is_assertion={found.get('is_assertion')} "
              f"sender={found.get('sender')!r}")
        print(f"       patents={nums}  {'CORRECT' if ok else 'WRONG'}")
        for pt in found.get("patents", []):
            print(f"       context: {pt.get('context','')[:110]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
