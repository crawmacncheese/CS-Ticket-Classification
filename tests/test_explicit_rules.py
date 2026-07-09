"""Tests for explicit rule engine extensions."""

from __future__ import annotations

from pathlib import Path

import pytest

from cs_tickets.classifier_rules import RuleSpec, set_active_rule_specs
from cs_tickets.classify import classify_row_with_explanation


def test_override_rule_beats_weighted_scoring(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    from cs_tickets.taxonomy import load_allowlist

    allow = load_allowlist(tax, xlsx)
    row = {
        "subject": "Stripe payment completed",
        "raw_subject": "Stripe payment completed",
        "description": "Stripe payment completed for order 123",
        "tags": "[]",
        "url": "",
    }
    normal = RuleSpec(
        id="test.normal.sales",
        tier=("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"),
        weight=15.0,
        any_blob=("stripe payment completed",),
    )
    override = RuleSpec(
        id="test.override.system",
        tier=("B2C", "Service Task", "Billing & Admin", "System Report", "N/A"),
        weight=20.0,
        override=True,
        any_blob=("stripe payment completed",),
    )
    decision = classify_row_with_explanation(row, allow, rule_specs=(normal, override))
    assert decision.tier == override.tier
    assert not decision.fallback_used
    assert any(ev.rule_id == override.id for ev in decision.evidence)


def test_disabled_rule_ignored(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    from cs_tickets.taxonomy import load_allowlist

    allow = load_allowlist(tax, xlsx)
    row = {
        "subject": "unique_disabled_probe_xyz",
        "raw_subject": "unique_disabled_probe_xyz",
        "description": "unique_disabled_probe_xyz body",
        "tags": "[]",
        "url": "",
    }
    disabled = RuleSpec(
        id="test.disabled.probe",
        tier=("B2C", "Service Task", "Billing & Admin", "System Report", "N/A"),
        weight=20.0,
        enabled=False,
        any_blob=("unique_disabled_probe_xyz",),
    )
    decision = classify_row_with_explanation(row, allow, rule_specs=(disabled,))
    assert not any(ev.rule_id == disabled.id for ev in decision.evidence)


def test_requester_domain_rule(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    from cs_tickets.taxonomy import load_allowlist

    allow = load_allowlist(tax, xlsx)
    row = {
        "subject": "refund help",
        "raw_subject": "refund help",
        "description": "please refund",
        "tags": "[]",
        "url": "",
        "requester_email": "user@privaterelay.appleid.com",
    }
    rule = RuleSpec(
        id="test.requester.domain",
        tier=("B2C", "Complaint", "Refund", "Refund Request", "N/A"),
        weight=12.0,
        any_requester_domain=("privaterelay.appleid.com",),
        any_blob=("refund",),
    )
    if rule.tier not in allow.tuples:
        pytest.skip("refund tuple not in allow-list")
    decision = classify_row_with_explanation(row, allow, rule_specs=(rule,))
    assert decision.tier == rule.tier


def test_rule_spec_new_fields_load_from_dict() -> None:
    from cs_tickets.classifier_rules import _rule_from_dict

    raw = {
        "id": "explicit.test",
        "tier": ["B2C", "Junk", "Junk", "PR / External Sales / Editorial Noise", "N/A"],
        "weight": 16.0,
        "override": True,
        "any_requester_domain": ["example.com"],
        "display_name": "Test Rule",
        "enabled": False,
    }
    rule = _rule_from_dict(raw)
    assert rule.override is True
    assert rule.display_name == "Test Rule"
    assert rule.enabled is False
    assert rule.any_requester_domain == ("example.com",)
