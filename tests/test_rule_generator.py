from __future__ import annotations

from cs_tickets.classifier_rules import RuleSpec, load_rule_specs
from cs_tickets.rule_coverage import rule_target_tiers
from cs_tickets.rule_generator import (
    ExemplarRuleSignals,
    generate_rule_from_exemplar,
    suggest_weight_for_exemplar,
)

RENEWAL = ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A")


def test_generate_skips_already_routable_tuple() -> None:
    rules = load_rule_specs()
    targets = rule_target_tiers(rules)
    exemplar = {"id": "1", "subject": "x", "tags": '["new_subscriber"]'}
    assert generate_rule_from_exemplar(exemplar, RENEWAL, existing_targets=targets) is None


def test_chat_shaped_rule_from_zopim_exemplar() -> None:
    exemplar = {
        "id": "42",
        "subject": "Conversation with agent",
        "description": "Help at account.scmp.com/manage",
        "tags": '["zopim_chat", "existing_subscriber"]',
        "url": "https://account.scmp.com/manage",
    }
    tier = ("B2C", "Service Task", "Sales Leads", "Novel Chat Tier", "N/A")
    generated = generate_rule_from_exemplar(exemplar, tier, existing_targets={})
    assert generated is not None
    assert generated.spec.any_tags or generated.spec.all_tags
    assert "account.scmp.com" in generated.spec.any_blob or "account.scmp.com" in generated.spec.any_url


def test_suggest_weight_uses_tier4_sibling_median() -> None:
    renewal = ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A")
    tier = (*renewal[:4], "Novel Granular")
    rules = (
        RuleSpec("a", renewal, 10.0, any_tags=("tag_a",)),
        RuleSpec("b", renewal, 12.0, any_tags=("tag_b",)),
    )
    signals = ExemplarRuleSignals(tags=("novel_tag",), any_tags=("novel_tag",))
    weight, warnings = suggest_weight_for_exemplar(tier, signals, rules)
    assert weight == 11.0
    assert any("sibling median" in w for w in warnings)


def test_suggest_weight_competition_bump() -> None:
    tier = ("B2C", "Service Task", "General Support", "Novel Tier", "N/A")
    rules = (RuleSpec("other", ("B2C", "Junk", "Junk", "Junk", "N/A"), 10.0, any_tags=("shared",)),)
    signals = ExemplarRuleSignals(tags=("shared",), any_tags=("shared",))
    weight, warnings = suggest_weight_for_exemplar(tier, signals, rules)
    assert weight == 11.0
    assert any("Tag overlap" in w for w in warnings)


def test_suggest_weight_contested_tier3_multi_signal() -> None:
    tier = ("B2C", "Complaint", "Technical Bug", "Novel Access Bug", "N/A")
    signals = ExemplarRuleSignals(
        tags=("product_issue",),
        any_tags=("product_issue",),
        any_blob=("cannot access",),
    )
    weight, _ = suggest_weight_for_exemplar(tier, signals, ())
    assert weight == 12.0


def test_suggest_weight_live_chat_tier4() -> None:
    tier = ("B2B", "Service Task", "General Support", "No Content - Live chat auto-trigger", "N/A")
    signals = ExemplarRuleSignals(tags=("zopim_chat",), any_tags=("zopim_chat",))
    weight, warnings = suggest_weight_for_exemplar(tier, signals, ())
    assert weight == 16.0
    assert any("Live-chat" in w for w in warnings)


def test_suggest_weight_blob_only_capped() -> None:
    tier = ("B2C", "Service Task", "General Support", "Novel Blob Tier", "N/A")
    signals = ExemplarRuleSignals(tags=(), any_blob=("phrase one", "phrase two"), blob_only=True)
    weight, warnings = suggest_weight_for_exemplar(tier, signals, ())
    assert weight == 9.0
    assert any("Blob-only" in w for w in warnings)


def test_generate_applies_sibling_weight_for_renewal_shaped_tier() -> None:
    exemplar = {
        "id": "77",
        "subject": "Unique renewal wording probe",
        "description": "Need pricing details for next term",
        "tags": '["unique_renewal_probe_tag"]',
    }
    tier = (
        "B2C",
        "Service Task",
        "Sales Leads",
        "Rate or Renewal Inquiry",
        "Novel Granular",
    )
    generated = generate_rule_from_exemplar(exemplar, tier, existing_targets={})
    assert generated is not None
    assert generated.spec.weight == 10.0


def test_b2b_printsupport_sets_context_flag() -> None:
    exemplar = {
        "id": "99",
        "subject": "Corporate gift order",
        "description": "gift subscription for team",
        "tags": '["print_subs"]',
        "url": "https://printsupport.scmp.com/form",
    }
    tier = ("B2B", "Service Task", "Sales Leads", "Novel Gift Tier", "N/A")
    generated = generate_rule_from_exemplar(exemplar, tier, existing_targets={})
    assert generated is not None
    assert generated.spec.requires_b2b_print_context is True
