"""Tests for category audit CSV export."""

from __future__ import annotations

from cs_tickets.category_audit_export import (
    CATEGORY_AUDIT_CSV_COLUMNS,
    category_audit_slice_csv_bytes,
)


def test_category_audit_csv_includes_description_and_tiers() -> None:
    rows = [
        {
            "id": "42",
            "subject": "Need help",
            "requester_email": "user@test.com",
            "description": "Full body text here",
            "Tier1_Segment": "B2C",
            "Tier2_Stream": "Complaint",
            "Tier3_Cat": "Refund",
            "Tier4_Type": "Cancellation Request",
            "Granular_Tech_UI_Type": "N/A",
            "tags": ["billing"],
            "created_at": "2025-06-01T00:00:00Z",
        }
    ]
    raw = category_audit_slice_csv_bytes(rows).decode("utf-8-sig")
    assert "id,subject,requester_email,description" in raw
    assert "Full body text here" in raw
    assert "Cancellation Request" in raw
    assert "billing" in raw
    for col in CATEGORY_AUDIT_CSV_COLUMNS:
        assert col in raw.splitlines()[0]
