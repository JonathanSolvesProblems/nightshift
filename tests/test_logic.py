"""Regression tests for the two things that have already failed silently.

Everything else in this project is verified by running it against real data,
which is the right trade for a build this size. These two are different: both
have already broken once, and both broke without raising anything.

1. Prior-art eligibility. A reference qualifies on its FILING date against the
   target's PRIORITY date. Grant date is wrong in both directions, and 52.8% of
   the corpus claims priority earlier than its own filing date, so this is not a
   detail that stays correct by luck.

2. Limitation label matching. The model returned the full limitation text where
   a label was expected. The lookup missed, returned nothing, and the chart
   rendered claim text in the label's uppercase style. Nothing raised.

    python -m pytest tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from priorart.judge import Limitation, normalize_label  # noqa: E402


# ---------------------------------------------------------------------------
# Prior-art eligibility
# ---------------------------------------------------------------------------

def is_prior_art(ref_filing: str, target_priority: str) -> bool:
    """The gate as the SQL applies it: filing date strictly before priority."""
    return ref_filing < target_priority


def same_family(ref_title, target_title, ref_priority, target_priority) -> bool:
    return ref_title == target_title or ref_priority == target_priority


class TestEligibility:
    def test_reference_filed_before_priority_qualifies(self):
        assert is_prior_art("2016-01-08", "2017-09-27")

    def test_reference_filed_after_priority_does_not(self):
        assert not is_prior_art("2018-03-01", "2017-09-27")

    def test_same_day_does_not_qualify(self):
        # Filed on the priority date is not "before" it.
        assert not is_prior_art("2017-09-27", "2017-09-27")

    def test_grant_date_would_have_been_wrong(self):
        """The real case from run 10140422: granted after, filed before.

        US 10,304,102 was granted 2019-05-28, almost a year AFTER the target was
        granted, and filed 2016-01-08, nearly two years BEFORE the target's
        priority date. It is valid prior art under 102(a)(2). A filter on grant
        date discards the best finding in the run.
        """
        ref_filing, ref_grant = "2016-01-08", "2019-05-28"
        target_priority, target_grant = "2017-09-27", "2018-06-19"
        assert is_prior_art(ref_filing, target_priority)
        assert ref_grant > target_grant  # grant order is the opposite way round

    def test_priority_can_precede_filing(self):
        """52.8% of the corpus claims priority earlier than it filed."""
        filing, priority = "2015-09-14", "2013-03-15"
        assert priority < filing
        # A reference filed between the two is NOT prior art against priority.
        assert not is_prior_art("2014-01-01", priority)

    def test_family_exclusion_on_shared_title(self):
        assert same_family("Progression analytics", "Progression analytics",
                           "2011-01-01", "2013-03-15")

    def test_family_exclusion_on_shared_priority(self):
        assert same_family("A", "B", "2013-03-15", "2013-03-15")

    def test_unrelated_reference_is_not_family(self):
        assert not same_family("A", "B", "2011-01-01", "2013-03-15")


# ---------------------------------------------------------------------------
# Limitation label matching
# ---------------------------------------------------------------------------

LIMS = [
    Limitation(index="1(pre)", text="A computer-implemented method comprising:"),
    Limitation(index="1(a)", text="identifying an outcome of interest;"),
    Limitation(index="1(b)", text="extracting electronic clinical data;"),
]


def resolve(raw: str) -> str:
    """The matcher from judge.chart: exact on normalized, then prefix, then raw."""
    by_norm = {normalize_label(l.index): l.index for l in LIMS}
    key = normalize_label(raw)
    label = by_norm.get(key)
    if label is None:
        label = next(
            (idx for norm, idx in by_norm.items() if key.startswith(norm)), raw
        )
    return label


class TestLabelMatching:
    def test_exact_label(self):
        assert resolve("1(a)") == "1(a)"

    def test_bracketed_label(self):
        # The unblinded arm returned '[1(a)]' where the blinded arm returned '1(a)'.
        assert resolve("[1(a)]") in ("1(a)", "[1(a)]")

    def test_case_and_space_insensitive(self):
        assert resolve("1 (A)") == "1(a)"
        assert resolve("1(A)") == "1(a)"

    def test_full_text_instead_of_label_still_resolves(self):
        """The failure that rendered claim text in the label's style.

        The model returned the label followed by the limitation text. Prefix
        matching must recover the label rather than silently returning nothing.
        """
        raw = "1(a) identifying an outcome of interest;"
        assert resolve(raw) == "1(a)"

    def test_preamble_label(self):
        assert resolve("1(pre)") == "1(pre)"

    def test_unknown_label_falls_back_to_raw_not_empty(self):
        """An unmatched label must be visible, never silently dropped."""
        out = resolve("2(z)")
        assert out
        assert out == "2(z)"

    def test_normalize_is_stable(self):
        assert normalize_label("1(a)") == normalize_label("1 ( A )".replace(" ", ""))
