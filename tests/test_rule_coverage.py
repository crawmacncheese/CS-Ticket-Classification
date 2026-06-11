from __future__ import annotations

from pathlib import Path

import pytest

from cs_tickets.classifier_rules import RuleSpec, load_rule_specs
from cs_tickets.rule_coverage import (
    computed_rule_targets,
    has_rule_target,
    scored_targets_from_source,
    training_routing_badge,
    tuple_rule_coverage,
)
from cs_tickets.taxonomy import AllowList, load_allowlist

RENEWAL = ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A")
NOVEL = ("NovelSeg", "NovelStream", "NovelCat", "NovelType", "NovelGran")


def test_sales_renewal_tuple_is_routable(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, ref)
    rules = load_rule_specs()
    cov = tuple_rule_coverage(RENEWAL, allow, json_rules=rules)
    assert cov.status == "routable"
    assert cov.rule_ids


def test_novel_in_allow_without_rule_is_allow_only(repo_root: Path) -> None:
    allow = AllowList(tuples=frozenset({NOVEL}))
    cov = tuple_rule_coverage(NOVEL, allow, json_rules=())
    assert cov.status == "allow_only"
    assert cov.rule_ids == ()


def test_rule_not_in_allow_is_blocked() -> None:
    allow = AllowList(tuples=frozenset())
    rule = RuleSpec(id="test.rule", tier=NOVEL, weight=10.0, any_tags=("test_tag",))
    cov = tuple_rule_coverage(NOVEL, allow, json_rules=(rule,))
    assert cov.status == "blocked"


def test_training_badge_needs_rule_for_novel_not_in_allow() -> None:
    badge = training_routing_badge(NOVEL, json_rules=())
    assert badge == "needs_rule"


def test_computed_targets_match_audit_ast(repo_root: Path) -> None:
    classify_py = repo_root / "src" / "cs_tickets" / "classify.py"
    computed = set(computed_rule_targets(classify_py))
    ast_set = scored_targets_from_source(classify_py)
    assert computed == ast_set


def test_has_rule_target_for_sales_new_subscriber() -> None:
    rules = load_rule_specs()
    assert has_rule_target(RENEWAL, json_rules=rules)
