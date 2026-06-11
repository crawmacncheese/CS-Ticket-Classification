from __future__ import annotations

import json
from pathlib import Path

import pytest

from cs_tickets.allowlist_compare import compare_allowlists_on_ndjson
from cs_tickets.classifier_rules import load_rule_specs
from cs_tickets.rule_generator import generate_rule_from_exemplar
from cs_tickets.taxonomy import AllowList, load_allowlist

PROBE_TUPLE = ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A")
NEGATIVE_TUPLE = ("TestSeg", "TestStream", "TestCat", "TestType", "TestGran")


def test_golden_export_tbc_within_baseline(repo_root: Path) -> None:
    golden = repo_root / "tests" / "fixtures" / "golden_export.ndjson"
    baseline_path = repo_root / "tests" / "fixtures" / "golden_baseline.json"
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not golden.is_file() or not tax.is_file() or not ref.is_file():
        pytest.skip("fixtures or doc missing")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    allow = load_allowlist(tax, ref)
    result = compare_allowlists_on_ndjson(golden, allow, allow)
    assert result.total == baseline["total"]
    assert result.tbc_old <= baseline["tbc_max"]
    assert result.zero_candidate_old <= baseline["zero_candidate_max"]


def test_training_probe_resolves_tbc_when_tuple_missing(repo_root: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not ndjson.is_file() or not tax.is_file() or not ref.is_file():
        pytest.skip("fixtures or doc missing")
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {PROBE_TUPLE}))
    allow_new = allow_full
    result = compare_allowlists_on_ndjson(ndjson, allow_old, allow_new)
    assert result.tbc_old == 1
    assert result.tbc_new == 0
    assert result.zero_candidate_old == 1
    assert result.zero_candidate_new == 0


def test_training_negative_control_tuple_without_rule_does_not_reduce_tbc(
    repo_root: Path,
) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not ndjson.is_file() or not tax.is_file() or not ref.is_file():
        pytest.skip("fixtures or doc missing")
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {NEGATIVE_TUPLE}))
    allow_new = AllowList(tuples=frozenset(allow_old.tuples | {NEGATIVE_TUPLE}))
    result = compare_allowlists_on_ndjson(ndjson, allow_old, allow_new)
    assert result.tbc_old == result.tbc_new
    assert result.zero_candidate_old == result.zero_candidate_new


def test_training_probe_resolves_zero_candidate_when_rule_generated(
    repo_root: Path, tmp_path: Path
) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("fixtures or doc missing")

    novel = ("ProbeOnlySeg", "ProbeOnlyStream", "ProbeOnlyCat", "ProbeOnlyType", "ProbeOnlyGran")
    allow_full = load_allowlist(tax, ref)
    allow_old = allow_full
    allow_new = AllowList(tuples=frozenset(allow_full.tuples | {novel}))

    exemplar = {
        "id": "999001",
        "subject": "Unique probe widget inquiry",
        "raw_subject": "Unique probe widget inquiry",
        "description": "Need help with probe widget configuration",
        "tags": '["probe_widget_tag"]',
        "url": "https://account.scmp.com/help",
    }
    generated = generate_rule_from_exemplar(exemplar, novel, existing_targets={})
    assert generated is not None

    probe = tmp_path / "probe.ndjson"
    probe.write_text(
        '{"id": 888001, "subject": "Unique probe widget inquiry", '
        '"raw_subject": "Unique probe widget inquiry", '
        '"description": "Need help with probe widget configuration", '
        '"tags": ["probe_widget_tag"]}\n',
        encoding="utf-8",
    )

    base = compare_allowlists_on_ndjson(probe, allow_old, allow_new)
    assert base.zero_candidate_old == 1

    with_rule = compare_allowlists_on_ndjson(
        probe,
        allow_old,
        allow_new,
        rule_specs_new=load_rule_specs() + (generated.spec,),
    )
    assert with_rule.zero_candidate_new < with_rule.zero_candidate_old
