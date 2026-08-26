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


# Which embedding the prefilter ranks with.
#
# The original `embedding_v1` from Google Patents Public Data is 64 dimensions
# from an unpublished model with no callable endpoint. gemini-embedding-001 at
# 768 dimensions replaced it after a measured comparison on the same gold pairs:
# recall at 2,000 candidates went from 54.0% to 83.9% for anticipation
# references, and the median rank of an examiner's reference fell from 1,230
# to 128. See ACCURACY.md.
#
# Both tables are kept so the comparison stays reproducible.
VECTOR_TABLE = os.environ.get("PRIOR_ART_VECTORS", "vectors_gemini_g06q")
VECTOR_COLUMN = os.environ.get("PRIOR_ART_VECTOR_COL", "embedding")


def vector_table(scope: str = "g06q") -> str:
    """The vector table for a scope, honouring the override."""
    name = VECTOR_TABLE
    if "{scope}" in name:
        name = name.format(scope=scope.lower())
    return working_table(name)
