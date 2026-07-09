"""Tests for AI category suggestion (TBC review helper)."""

from __future__ import annotations

from cs_tickets.category_suggest import suggest_category_for_ticket
from cs_tickets.taxonomy import load_allowlist


def test_suggest_without_llm_uses_classifier_candidate(repo_root) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        import pytest

        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {"id": "1", "subject": "test", "description": "Stripe payment completed", "tags": "[]"}
    explain = {
        "tier": ["B2C", "Service Task", "General Support", "TBC (Manual Review)", "N/A"],
        "fallback_used": True,
        "candidates": [
            {
                "tier": ["B2C", "Service Task", "Billing & Admin", "System Report", "N/A"],
                "score": 4.0,
            }
        ],
        "evidence": [],
        "tbc_reason": "below_threshold",
    }
    result = suggest_category_for_ticket(
        row,
        allow,
        explain_payload=explain,
        use_llm=False,
    )
    assert result.ok
    assert result.source == "classifier"
    assert "System Report" in result.tier_path
    assert "TBC" not in result.tier_path
    assert "TBC (Manual Review)" not in result.prefill


def test_suggest_without_llm_or_candidate_returns_error(repo_root) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        import pytest

        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {"id": "1", "subject": "???", "description": "", "tags": "[]"}
    explain = {
        "tier": ["B2C", "Service Task", "General Support", "TBC (Manual Review)", "N/A"],
        "fallback_used": True,
        "candidates": [],
        "evidence": [],
    }
    result = suggest_category_for_ticket(row, allow, explain_payload=explain, use_llm=False)
    assert not result.ok
    assert result.errors
