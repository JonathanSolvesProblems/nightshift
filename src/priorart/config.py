"""Central configuration.

Everything that names a Google Cloud resource lives here so the README spin-up
instructions have exactly one place to point at.
"""

from __future__ import annotations

import os

# Google Cloud project holding the working corpus. BigQuery sandbox is enough
# for the corpus work; Cloud Run and Vertex AI need billing attached.
PROJECT_ID = os.environ.get("PRIOR_ART_PROJECT", "prior-art-agent-2026")

# Dataset I own, holding the materialized working corpus. The public tables are
# too expensive to query per request (see docs/DAY1-FINDINGS.md), so the design
# is materialize once and read many.
DATASET = os.environ.get("PRIOR_ART_DATASET", "corpus")
LOCATION = os.environ.get("PRIOR_ART_LOCATION", "US")

# Public source tables. patentsview is US-only and normalized, which makes it an
# order of magnitude cheaper to scan than the global flat publications table.
SRC_CPC = "patents-public-data.patentsview.cpc_current"
SRC_PATENT = "patents-public-data.patentsview.patent"
SRC_CLAIM = "patents-public-data.patentsview.claim"
SRC_VECTORS = "patents-public-data.google_patents_research.vector_db"

# Cap on stored disclosure text per candidate patent. Full descriptions are over
# 1 TB across the corpus, so I store abstract plus claims and cap the length.
# Screening asks what a reference discloses, and abstract plus claims carries
# most of that signal at a fraction of the size.
MAX_DISCLOSURE_CHARS = 20_000

# BigQuery sandbox allowance. Used to refuse queries that would eat the budget.
FREE_TIER_BYTES = 1024**4  # 1 TiB per month
DEFAULT_SCAN_CEILING_GB = float(os.environ.get("PRIOR_ART_SCAN_CEILING_GB", "150"))


def working_table(name: str) -> str:
    """Fully qualified name of a table in my own dataset."""
    return f"{PROJECT_ID}.{DATASET}.{name}"
