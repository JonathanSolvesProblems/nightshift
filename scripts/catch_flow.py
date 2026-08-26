"""Screenshot the run page repeatedly while a run is in flight.

The cut face only renders while candidates are actually being screened, so a
finished run shows empty lanes. This waits for the shards to start reporting and
then captures a burst, which is the only way to see whether the flow is real.
"""

import sys
import time

sys.path.insert(0, r"C:\Users\Jon_A\OneDrive\Desktop\Projects\Time3\AllThingsAgentic\src")

from playwright.sync_api import sync_playwright

from priorart import store

BASE = "https://nightshift-1015687974010.us-central1.run.app"
RID = sys.argv[1]

# Wait for the first shard to report, or give up.
for _ in range(50):
    sh = store.list_shards(RID)
    if sh and sum(s.get("screened", 0) for s in sh) > 0:
        print(f"shards reporting: {len(sh)}, screened "
              f"{sum(s.get('screened',0) for s in sh)}", flush=True)
        break
    time.sleep(10)
else:
    print("run never started reporting", flush=True)
    sys.exit(1)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 900},
                        device_scale_factor=2)
    page = ctx.new_page()
    page.goto(f"{BASE}/run/{RID}", wait_until="networkidle", timeout=120_000)
    for i in range(6):
        page.wait_for_timeout(2600)
        out = f"docs/shots/flow-{i}.png"
        page.screenshot(path=out)
        print(f"  {out}", flush=True)
    b.close()
