from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs_tickets.classifier_rules import RuleSpec, load_rule_specs, reload_rule_specs, set_active_rule_specs


def test_load_rule_specs_includes_core_rules() -> None:
    rules = load_rule_specs()
    assert any(r.id == "sales.new_subscriber.b2c" for r in rules)


def test_reload_picks_up_training_rules(repo_root: Path, tmp_path: Path, monkeypatch) -> None:
    doc = tmp_path / "doc"
    doc.mkdir()
    rules_path = doc / "training_rules.json"
    entry = {
        "id": "training.test.rule",
        "source": "training_commit",
        "exemplar_id": "1",
        "tuple_key": "abc123",
        "tier": ["X", "Y", "Z", "W", "N/A"],
        "weight": 10.0,
        "any_tags": ["test_training_tag"],
    }
    rules_path.write_text(json.dumps([entry]), encoding="utf-8")

    monkeypatch.setattr("cs_tickets.classifier_rules.training_rules_path", lambda: rules_path)
    reload_rule_specs()
    rules = load_rule_specs()
    assert any(r.id == "training.test.rule" for r in rules)
    assert any(r.tuple_key == "abc123" for r in rules)


def test_set_active_rule_specs_invalidates_cached_load_rule_specs() -> None:
    set_active_rule_specs(())
    first = load_rule_specs()
    updated = (
        RuleSpec(
            id="runtime.cache.probe",
            tier=("B2C", "Service Task", "General Support", "TBC (Manual Review)", "N/A"),
            weight=10.0,
            any_tags=("cache_probe",),
        ),
    )
    set_active_rule_specs(updated)
    second = load_rule_specs()
    assert first != second
    assert any(r.id == "runtime.cache.probe" for r in second)
    set_active_rule_specs(None)
    load_rule_specs.cache_clear()
