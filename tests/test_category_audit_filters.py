"""Tests for category audit slice filters."""

from __future__ import annotations

from cs_tickets.category_audit_filters import (
    CategoryAuditFilter,
    category_audit_url,
    filter_category_audit_rows,
    row_matches_category_audit_filter,
)
from cs_tickets.schema import TIER_FALLBACK_B2C_TBC


def _row(
    tid: str,
    *,
    tier1: str = "B2C",
    tier4: str = "Cancellation Request",
    subject: str = "cancel please",
    tbc: bool = False,
) -> dict:
    tier4_val = TIER_FALLBACK_B2C_TBC[3] if tbc else tier4
    return {
        "id": tid,
        "subject": subject,
        "description": "",
        "tags": "[]",
        "Tier1_Segment": tier1,
        "Tier2_Stream": "Complaint",
        "Tier3_Cat": "Refund",
        "Tier4_Type": tier4_val,
        "Granular_Tech_UI_Type": "N/A",
    }


def test_filter_b2c_cancellation_excludes_tbc_by_default() -> None:
    rows = [
        _row("1", tier4="Cancellation Request"),
        _row("2", tbc=True),
        _row("3", tier1="B2B", tier4="Cancellation Request"),
    ]
    filt = CategoryAuditFilter(tier1="B2C", tier4="Cancellation Request")
    out = filter_category_audit_rows(rows, filt)
    assert [r["id"] for r in out] == ["1"]


def test_filter_tbc_tier4_includes_manual_review_rows() -> None:
    rows = [
        _row("1", tier1="B2C", tbc=True),
        _row("2", tier1="B2C", tbc=True),
        _row("3", tier1="B2C", tier4="Cancellation Request"),
    ]
    filt = CategoryAuditFilter(
        tier1="B2C",
        tier4=TIER_FALLBACK_B2C_TBC[3],
    )
    out = filter_category_audit_rows(rows, filt)
    assert [r["id"] for r in out] == ["1", "2"]
    assert filt.includes_tbc_rows() is True


def test_filter_include_tbc_adds_manual_review_rows() -> None:
    rows = [_row("1"), _row("2", tbc=True)]
    filt = CategoryAuditFilter(include_tbc=True)
    out = filter_category_audit_rows(rows, filt)
    assert len(out) == 2


def test_filter_categories_substring_match() -> None:
    row = _row("1", tier4="Access Loop or App Bug")
    filt = CategoryAuditFilter(categories=("access loop",))
    assert row_matches_category_audit_filter(row, filt) is True


def test_filter_q_matches_subject() -> None:
    row = _row("1", subject="URGENT stripe payment issue")
    filt = CategoryAuditFilter(q="stripe")
    assert row_matches_category_audit_filter(row, filt) is True


def test_category_audit_url_builds_query() -> None:
    url = category_audit_url(
        "abc",
        CategoryAuditFilter(tier1="B2C", tier4="Cancellation Request"),
    )
    assert url == "/run/abc/category_audit?tier1=B2C&tier4=Cancellation+Request"
