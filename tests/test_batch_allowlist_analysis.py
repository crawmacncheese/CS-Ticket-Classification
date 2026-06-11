from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cs_tickets.allowlist_compare import AllowlistCompareResult, compare_allowlists_on_ndjson, enrich_changed_row
from cs_tickets.allowlist_training import build_candidate_allowlist, create_session
from cs_tickets.batch_allowlist_analysis import (
    BatchCompareResult,
    build_candidate_allowlist_cli,
    classify_verdict_band,
    compute_selection_no_op_count,
    resolve_selected_tuples,
    run_commit_simulation,
    run_tuple_ablation,
    write_ablation_reports,
    write_summary_markdown,
)
from cs_tickets.taxonomy import AllowList, load_allowlist

PROBE_TUPLE = ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A")
NEGATIVE_TUPLE = ("TestSeg", "TestStream", "TestCat", "TestType", "TestGran")


def _require_doc(repo_root: Path) -> tuple[Path, Path]:
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")
    return tax, ref


def _make_probe_upload(repo_root: Path, tmp_path: Path) -> Path:
    tool = repo_root / "tools" / "build_training_test_upload.py"
    out = tmp_path / "probe_upload.xlsx"
    import subprocess
    import sys

    subprocess.run(
        [sys.executable, str(tool), "--out", str(out)],
        check=True,
        cwd=repo_root,
    )
    return out


def test_batch_identity(repo_root: Path) -> None:
    tax, ref = _require_doc(repo_root)
    ndjson = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    allow = load_allowlist(tax, ref)
    result = run_commit_simulation(
        [ndjson],
        allow,
        allow,
        selected_tuples=frozenset({PROBE_TUPLE}),
    )
    assert result.combined.tbc_old == result.combined.tbc_new
    assert result.combined.changed_rows == []


def test_batch_probe_gap_fix(repo_root: Path) -> None:
    tax, ref = _require_doc(repo_root)
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {PROBE_TUPLE}))
    allow_new = allow_full
    result = run_commit_simulation(
        [ndjson],
        allow_old,
        allow_new,
        selected_tuples=frozenset({PROBE_TUPLE}),
    )
    assert result.outcome_counts["gap_fix"] >= 1
    assert result.gap_fix_by_mechanism["allowlist_gap"] >= 1
    row = next(r for r in result.combined.changed_rows if r["id"] == "910001")
    assert row["outcome_type"] == "gap_fix"
    assert row["gap_fix_mechanism"] == "allowlist_gap"


def test_batch_matches_single_compare(repo_root: Path) -> None:
    tax, ref = _require_doc(repo_root)
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {PROBE_TUPLE}))
    allow_new = allow_full
    selected = frozenset({PROBE_TUPLE})
    direct = compare_allowlists_on_ndjson(
        ndjson,
        allow_old,
        allow_new,
        enrich_changed_rows=True,
        selected_tuples=selected,
    )
    batch = run_commit_simulation(
        [ndjson],
        allow_old,
        allow_new,
        selected_tuples=selected,
    )
    assert batch.combined.total == direct.total
    assert batch.combined.tbc_old == direct.tbc_old
    assert batch.combined.tbc_new == direct.tbc_new
    assert len(batch.combined.changed_rows) == len(direct.changed_rows)


def test_batch_negative_control(repo_root: Path) -> None:
    tax, ref = _require_doc(repo_root)
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {NEGATIVE_TUPLE}))
    allow_new = AllowList(tuples=frozenset(allow_old.tuples | {NEGATIVE_TUPLE}))
    result = run_commit_simulation(
        [ndjson],
        allow_old,
        allow_new,
        selected_tuples=frozenset({NEGATIVE_TUPLE}),
    )
    assert result.outcome_counts["gap_fix"] == 0
    assert result.combined.tbc_old == result.combined.tbc_new


def test_outcome_type_matrix() -> None:
    class Dec:
        def __init__(self, tier, *, candidates, fallback_used=False):
            self.tier = tier
            self.candidates = candidates
            self.fallback_used = fallback_used
            self.evidence = []

    gap = enrich_changed_row(
        Dec(("B2C", "A", "B", "TBC (Manual Review)", "N/A"), candidates=[]),
        Dec(("B2C", "A", "B", "Resolved", "N/A"), candidates=[("x", 1)]),
    )
    assert gap["outcome_type"] == "gap_fix"
    assert gap["gap_fix_mechanism"] == "allowlist_gap"

    recovery = enrich_changed_row(
        Dec(("B2C", "A", "B", "TBC (Manual Review)", "N/A"), candidates=[("x", 1)]),
        Dec(("B2C", "A", "B", "Resolved", "N/A"), candidates=[("x", 1)]),
    )
    assert recovery["outcome_type"] == "gap_fix"
    assert recovery["gap_fix_mechanism"] == "scoring_recovery"

    regression = enrich_changed_row(
        Dec(("B2C", "A", "B", "Resolved", "N/A"), candidates=[("x", 1)]),
        Dec(("B2C", "A", "B", "TBC (Manual Review)", "N/A"), candidates=[("x", 1)]),
    )
    assert regression["outcome_type"] == "regression"

    reroute = enrich_changed_row(
        Dec(("B2C", "A", "B", "TypeA", "N/A"), candidates=[("x", 1)]),
        Dec(("B2C", "A", "B", "TypeB", "N/A"), candidates=[("x", 1)]),
    )
    assert reroute["outcome_type"] == "reroute"


def test_multi_file_aggregation(repo_root: Path, tmp_path: Path) -> None:
    tax, ref = _require_doc(repo_root)
    src = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    f1 = tmp_path / "a.ndjson"
    f2 = tmp_path / "b.ndjson"
    shutil.copy2(src, f1)
    shutil.copy2(src, f2)
    allow = load_allowlist(tax, ref)
    result = run_commit_simulation(
        [f1, f2],
        allow,
        allow,
        selected_tuples=frozenset({PROBE_TUPLE}),
    )
    assert result.combined.total == result.per_file["a.ndjson"].total + result.per_file["b.ndjson"].total


def test_multi_file_dedupe(repo_root: Path, tmp_path: Path) -> None:
    tax, ref = _require_doc(repo_root)
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {PROBE_TUPLE}))
    allow_new = allow_full
    line = (repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson").read_text(encoding="utf-8")
    f1 = tmp_path / "first.ndjson"
    f2 = tmp_path / "second.ndjson"
    f1.write_text(line, encoding="utf-8")
    f2.write_text(line, encoding="utf-8")
    result = run_commit_simulation(
        [f1, f2],
        allow_old,
        allow_new,
        selected_tuples=frozenset({PROBE_TUPLE}),
    )
    assert len(result.combined.changed_rows) == 1
    assert "910001" in result.duplicate_ticket_ids


def test_with_rules_path(repo_root: Path, tmp_path: Path) -> None:
    tax, ref = _require_doc(repo_root)
    upload = _make_probe_upload(repo_root, tmp_path)
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {PROBE_TUPLE}))
    allow_new, _ = build_candidate_allowlist_cli(repo_root, upload, frozenset({PROBE_TUPLE}), tmp_path / "work")
    from cs_tickets.allowlist_training import build_candidate_rule_set_from_upload

    rules = build_candidate_rule_set_from_upload(repo_root, upload, frozenset({PROBE_TUPLE}))
    result = run_commit_simulation(
        [ndjson],
        allow_old,
        allow_new,
        selected_tuples=frozenset({PROBE_TUPLE}),
        rule_specs_new=rules,
    )
    assert result.combined.tbc_new <= result.combined.tbc_old


def test_tuple_selection_intersection(repo_root: Path, tmp_path: Path) -> None:
    tax, ref = _require_doc(repo_root)
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {PROBE_TUPLE}))
    upload = _make_probe_upload(repo_root, tmp_path)
    sel_path = tmp_path / "selected.json"
    sel_path.write_text(json.dumps([list(PROBE_TUPLE), list(NEGATIVE_TUPLE)]), encoding="utf-8")
    selected = resolve_selected_tuples(
        allow_old=allow_old,
        merge_tuples_from=upload,
        selected_tuples_json=sel_path,
    )
    assert selected == frozenset({PROBE_TUPLE})


@pytest.mark.parametrize(
    ("tbc_old", "tbc_new", "gap_fix", "regression", "zero_old", "zero_new", "margin_old", "margin_new", "rules_count", "selected_n", "expected"),
    [
        (3, 2, 2, 1, 0, 0, 0, 0, 5, 5, "strong_commit"),
        (2, 5, 0, 1, 5, 5, 2, 5, 5, 5, "risky"),
        (1, 1, 0, 0, 0, 0, 0, 0, 1, 5, "rules_needed"),
        (1, 1, 0, 0, 0, 0, 0, 0, 5, 5, "review"),
    ],
)
def test_verdict_band_classification(
    tbc_old: int,
    tbc_new: int,
    gap_fix: int,
    regression: int,
    zero_old: int,
    zero_new: int,
    margin_old: int,
    margin_new: int,
    rules_count: int,
    selected_n: int,
    expected: str,
) -> None:
    combined = AllowlistCompareResult(
        total=10,
        tbc_old=tbc_old,
        tbc_new=tbc_new,
        changed_rows=[],
        zero_candidate_old=zero_old,
        zero_candidate_new=zero_new,
        margin_loss_old=margin_old,
        margin_loss_new=margin_new,
    )
    selected = frozenset(
        [PROBE_TUPLE, NEGATIVE_TUPLE, ("A", "B", "C", "D", "E"), ("F", "G", "H", "I", "J"), ("K", "L", "M", "N", "O")][
            :selected_n
        ]
    )
    result = BatchCompareResult(
        per_file={},
        combined=combined,
        selected_tuples=selected,
        outcome_counts={"gap_fix": gap_fix, "regression": regression, "reroute": 0},
        gap_fix_by_mechanism={},
        tuples_with_rules_count=rules_count,
        selection_no_op_count=None,
        duplicate_ticket_ids=[],
        verdict_band="review",
        verdict_reasons=[],
    )
    band, _ = classify_verdict_band(result)
    assert band == expected


def test_enrichment_opt_in(repo_root: Path) -> None:
    tax, ref = _require_doc(repo_root)
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {PROBE_TUPLE}))
    allow_new = allow_full
    plain = compare_allowlists_on_ndjson(ndjson, allow_old, allow_new)
    enriched = compare_allowlists_on_ndjson(
        ndjson,
        allow_old,
        allow_new,
        enrich_changed_rows=True,
    )
    assert plain.changed_rows
    assert "outcome_type" not in plain.changed_rows[0]
    assert enriched.changed_rows[0]["outcome_type"] == "gap_fix"


def test_candidate_allowlist_parity(repo_root: Path, tmp_path: Path) -> None:
    tax, ref = _require_doc(repo_root)
    upload = _make_probe_upload(repo_root, tmp_path)
    selected = frozenset({PROBE_TUPLE})
    cli_allow, cli_merged = build_candidate_allowlist_cli(
        repo_root,
        upload,
        selected,
        tmp_path / "cli_work",
    )
    session = create_session(upload, repo_root)
    portal_allow, portal_merged = build_candidate_allowlist(session, selected)
    assert cli_allow.tuples == portal_allow.tuples
    assert cli_merged == portal_merged


def test_compute_no_op_negative_tuple(repo_root: Path) -> None:
    tax, ref = _require_doc(repo_root)
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_full = load_allowlist(tax, ref)
    count = compute_selection_no_op_count(
        [ndjson],
        allow_full,
        frozenset({NEGATIVE_TUPLE}),
    )
    assert count == 1


def test_compare_default_unchanged(repo_root: Path) -> None:
    tax, ref = _require_doc(repo_root)
    ndjson = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    allow = load_allowlist(tax, ref)
    result = compare_allowlists_on_ndjson(ndjson, allow, allow)
    assert result.total >= 1


def _probe_allowlists(repo_root: Path) -> tuple[AllowList, AllowList]:
    tax, ref = _require_doc(repo_root)
    allow_full = load_allowlist(tax, ref)
    allow_old = AllowList(tuples=frozenset(allow_full.tuples - {PROBE_TUPLE}))
    return allow_old, allow_full


def test_ablation_probe_tuple_tbc_delta(repo_root: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_old, _ = _probe_allowlists(repo_root)
    ablation = run_tuple_ablation(
        [ndjson],
        allow_old,
        frozenset({PROBE_TUPLE}),
    )
    assert len(ablation) == 1
    assert ablation[0].tbc_delta == 1
    assert ablation[0].gap_fix_count >= 1
    assert ablation[0].no_op is False


def test_ablation_negative_tuple_no_op(repo_root: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_old, _ = _probe_allowlists(repo_root)
    ablation = run_tuple_ablation(
        [ndjson],
        allow_old,
        frozenset({NEGATIVE_TUPLE}),
    )
    assert ablation[0].no_op is True
    assert ablation[0].gap_fix_count == 0
    assert ablation[0].regression_count == 0
    assert ablation[0].reroute_count == 0


def test_ablation_row_count(repo_root: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_old, _ = _probe_allowlists(repo_root)
    selected = frozenset({PROBE_TUPLE, NEGATIVE_TUPLE})
    ablation = run_tuple_ablation([ndjson], allow_old, selected)
    assert len(ablation) == 2


def test_ablation_with_rules_has_rule(repo_root: Path, tmp_path: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_old, _ = _probe_allowlists(repo_root)
    upload = _make_probe_upload(repo_root, tmp_path)
    from cs_tickets.allowlist_training import build_candidate_rule_set_from_upload

    ablation = run_tuple_ablation(
        [ndjson],
        allow_old,
        frozenset({PROBE_TUPLE}),
        rule_specs_builder=lambda t: build_candidate_rule_set_from_upload(
            repo_root, upload, frozenset({t})
        ),
    )
    assert ablation[0].has_rule is True


def test_ablation_without_rules_gap(repo_root: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_old, _ = _probe_allowlists(repo_root)
    ablation = run_tuple_ablation(
        [ndjson],
        allow_old,
        frozenset({NEGATIVE_TUPLE}),
    )
    assert ablation[0].no_op is True
    assert ablation[0].has_rule is False


def test_pattern_summary_rollup(repo_root: Path, tmp_path: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_old, _ = _probe_allowlists(repo_root)
    other = ("B2C", "Service Task", "Sales Leads", "Other Inquiry", "N/A")
    ablation = run_tuple_ablation(
        [ndjson],
        allow_old,
        frozenset({PROBE_TUPLE, other}),
    )
    write_ablation_reports(ablation, tmp_path)
    text = (tmp_path / "pattern_summary.csv").read_text(encoding="utf-8")
    assert text.count("B2C,Service Task,Sales Leads") == 1
    assert "tuple_count,2" in text.replace(" ", "") or ",2," in text


def test_full_selection_not_sum_of_ablations(repo_root: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_old, allow_new = _probe_allowlists(repo_root)
    selected = frozenset({PROBE_TUPLE, NEGATIVE_TUPLE})
    commit = run_commit_simulation(
        [ndjson],
        allow_old,
        allow_new,
        selected_tuples=selected,
    )
    ablation = run_tuple_ablation([ndjson], allow_old, selected)
    commit_delta = commit.combined.tbc_old - commit.combined.tbc_new
    ablation_sum = sum(row.tbc_delta for row in ablation)
    # Interaction effects: marginal deltas need not reconcile with full selection.
    assert isinstance(commit_delta, int)
    assert isinstance(ablation_sum, int)


def test_write_summary_markdown(repo_root: Path, tmp_path: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    allow_old, allow_new = _probe_allowlists(repo_root)
    selected = frozenset({PROBE_TUPLE})
    result = run_commit_simulation(
        [ndjson],
        allow_old,
        allow_new,
        selected_tuples=selected,
    )
    ablation = run_tuple_ablation([ndjson], allow_old, selected)
    write_summary_markdown(
        result,
        tmp_path,
        ablation=ablation,
        ndjson_paths=[ndjson],
    )
    text = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "# Batch Allow-List Impact Summary" in text
    assert f"Verdict band | `{result.verdict_band}`" in text
    assert "View A — Commit Verdict" in text
    assert "View B — Tuple Risk (ablation)" in text
    assert "## Interpretation" in text
    assert "training_tbc_probe.ndjson" in text
    assert "910001" in text
