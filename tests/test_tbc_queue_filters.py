"""Tests for TBC queue keyword + category filters."""

from __future__ import annotations

from cs_tickets.tbc_queue_filters import TbcQueueFilter, row_matches_tbc_filter


def test_contains_filter_matches_subject() -> None:
    row = {
        "id": "1",
        "subject": "Question from Sherina about print delivery",
        "description": "",
        "tags": "[]",
        "Tier1_Segment": "B2C",
        "Tier2_Stream": "Service Task",
        "Tier3_Cat": "General Support",
        "Tier4_Type": "TBC (Manual Review)",
        "Granular_Tech_UI_Type": "N/A",
    }
    explain = {"candidates": [], "suggested_tier": "infer"}
    filt = TbcQueueFilter(q="sherina")
    assert row_matches_tbc_filter(row, explain, filt)


def test_category_filter_matches_candidate_path() -> None:
    row = {
        "id": "2",
        "subject": "paid but locked out",
        "description": "",
        "tags": "[]",
        "Tier1_Segment": "B2C",
        "Tier2_Stream": "Service Task",
        "Tier3_Cat": "General Support",
        "Tier4_Type": "TBC (Manual Review)",
        "Granular_Tech_UI_Type": "N/A",
    }
    explain = {
        "candidates": [
            {
                "tier": [
                    "B2C",
                    "Complaint",
                    "Technical Bug",
                    "Access Loop or App Bug",
                    "N/A",
                ],
                "score": 4.0,
            }
        ],
        "suggested_tier": "B2C → Complaint → Technical Bug → Access Loop or App Bug",
    }
    filt = TbcQueueFilter(tier1="B2C", categories=("Access Loop",))
    assert row_matches_tbc_filter(row, explain, filt)

    filt_cancel = TbcQueueFilter(categories=("Cancellation",))
    assert not row_matches_tbc_filter(row, explain, filt_cancel)


def test_tier1_and_category_combined() -> None:
    row = {
        "id": "3",
        "subject": "cancel my sub",
        "Tier1_Segment": "B2C",
        "Tier2_Stream": "Complaint",
        "Tier3_Cat": "Refund",
        "Tier4_Type": "TBC (Manual Review)",
        "Granular_Tech_UI_Type": "N/A",
    }
    explain = {
        "candidates": [
            {"tier": ["B2C", "Complaint", "Refund", "Cancellation Request", "N/A"], "score": 3.0}
        ]
    }
    filt = TbcQueueFilter(tier1="B2C", categories=("Cancellation",))
    assert row_matches_tbc_filter(row, explain, filt)
