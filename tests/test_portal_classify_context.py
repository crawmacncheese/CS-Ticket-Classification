"""Tests for TBC prefill and suggestion helpers."""

from __future__ import annotations

from cs_tickets.portal_classify_context import (
    build_tbc_rule_prefill,
    suggest_tier_for_prefill,
)


def test_suggest_tier_zero_rules_does_not_return_tbc_fallback() -> None:
    explain = {
        "tier": ["B2C", "Service Task", "General Support", "TBC (Manual Review)", "N/A"],
        "fallback_used": True,
        "candidates": [],
        "evidence": [],
    }
    assert suggest_tier_for_prefill(explain) == "infer from ticket content (no rule match)"


def test_suggest_tier_shows_top_candidate_when_present() -> None:
    explain = {
        "tier": ["B2C", "Service Task", "General Support", "TBC (Manual Review)", "N/A"],
        "fallback_used": True,
        "candidates": [
            {
                "tier": ["B2C", "Service Task", "Billing & Admin", "System Report", "N/A"],
                "score": 4.0,
            }
        ],
        "evidence": [{"rule_id": "billing.stripe"}],
    }
    hint = suggest_tier_for_prefill(explain)
    assert "System Report" in hint
    assert "top candidate" in hint


def test_build_tbc_rule_prefill_anchors_on_content_not_tbc() -> None:
    row = {
        "subject": "Stripe payment completed",
        "description": "Your payment was processed successfully.",
    }
    explain = {
        "fallback_used": True,
        "tbc_reason": "zero_candidate",
        "tbc_reason_detail": "zero_candidate",
        "candidates": [],
        "evidence": [],
        "tier": ["B2C", "Service Task", "General Support", "TBC (Manual Review)", "N/A"],
    }
    prefill = build_tbc_rule_prefill(ticket_id="123", row=row, explain=explain)
    assert "Stripe payment completed" in prefill
    assert "TBC (Manual Review)" not in prefill
    assert "Update: Map" in prefill
    assert "not manual review" in prefill.lower() or "not Manual review" in prefill
