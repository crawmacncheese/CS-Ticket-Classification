from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cs_tickets.allowlist_compare import (
    AllowlistCompareResult,
    compare_allowlists_on_ndjson,
    enrich_changed_row,
)
from cs_tickets.allowlist_training import build_candidate_rule_set_from_upload
from cs_tickets.classifier_rules import RuleSpec, load_rule_specs
from cs_tickets.classify import classify_row_with_explanation
from cs_tickets.thread_enrich import (
    build_ticket_index,
    flatten_for_classify,
    thread_enrichment_enabled,
)
from cs_tickets.pipeline import _iter_ticket_dicts
from cs_tickets.rule_coverage import computed_rule_targets, has_rule_target
from cs_tickets.taxonomy import (
    AllowList,
    diff_against_allowlist,
    extract_classified_workbook_five_tuples,
    load_allowlist,
    merge_tuples_into_workbook,
)

FiveTuple = tuple[str, str, str, str, str]
OldCache = dict[str, list[tuple[dict, Any]]]


@dataclass(frozen=True)
class BatchCompareResult:
    per_file: dict[str, AllowlistCompareResult]
    combined: AllowlistCompareResult
    selected_tuples: frozenset[FiveTuple]
    outcome_counts: dict[str, int]
    gap_fix_by_mechanism: dict[str, int]
    tuples_with_rules_count: int
    selection_no_op_count: int | None
    duplicate_ticket_ids: list[str]
    verdict_band: str
    verdict_reasons: list[str]


@dataclass(frozen=True)
class TupleAblationResult:
    five_tuple: FiveTuple
    tbc_delta: int
    gap_fix_count: int
    regression_count: int
    reroute_count: int
    no_op: bool
    has_rule: bool
    segment: str
    stream: str
    cat: str


def _is_tbc(decision) -> bool:
    return decision.fallback_used or "tbc" in decision.tier[3].lower()


def parse_inline_tuple(raw: str) -> FiveTuple:
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 5:
        raise ValueError(f"Expected 5 comma-separated tiers, got {len(parts)}: {raw!r}")
    return tuple(parts)  # type: ignore[return-value]


def load_tuples_json(path: Path) -> frozenset[FiveTuple]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("selected-tuples-json must be a JSON array of 5-tuples")
    out: set[FiveTuple] = set()
    for item in data:
        if isinstance(item, list) and len(item) == 5:
            out.add(tuple(str(x) for x in item))
        elif isinstance(item, str):
            out.add(parse_inline_tuple(item))
        else:
            raise ValueError(f"Invalid tuple entry: {item!r}")
    return frozenset(out)


def resolve_selected_tuples(
    *,
    allow_old: AllowList,
    inline_tuples: list[FiveTuple] | None = None,
    merge_tuples_from: Path | None = None,
    selected_tuples_json: Path | None = None,
) -> frozenset[FiveTuple]:
    selected: set[FiveTuple] = set(inline_tuples or ())
    if selected_tuples_json is not None:
        selected |= set(load_tuples_json(selected_tuples_json))

    if merge_tuples_from is not None:
        upload_tuples = extract_classified_workbook_five_tuples(merge_tuples_from)
        novel = diff_against_allowlist(upload_tuples, allow_old)
        if selected_tuples_json is not None or inline_tuples:
            selected &= novel
        else:
            selected |= novel

    if not selected:
        raise ValueError("Empty tuple selection after resolving inputs")
    return frozenset(selected)


def build_candidate_allowlist_cli(
    repo_root: Path,
    upload_path: Path,
    selected: frozenset[FiveTuple],
    work_dir: Path,
) -> tuple[AllowList, int]:
    tax_path = repo_root / "doc" / "Taxonomy.csv"
    wb_path = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    candidate_wb = work_dir / "candidate_workbook.xlsx"
    work_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(wb_path, candidate_wb)
    merged = merge_tuples_into_workbook(candidate_wb, upload_path, selected)
    return load_allowlist(tax_path, candidate_wb), merged


def count_tuples_with_rules(
    selected: frozenset[FiveTuple],
    *,
    rule_specs_new: tuple[RuleSpec, ...] | None = None,
) -> int:
    rules = rule_specs_new if rule_specs_new is not None else load_rule_specs()
    computed = computed_rule_targets()
    return sum(1 for t in selected if has_rule_target(t, json_rules=rules, computed_targets=computed))


def _sum_compare_results(
    per_file: dict[str, AllowlistCompareResult],
    *,
    selected_tuples: frozenset[FiveTuple],
) -> tuple[AllowlistCompareResult, list[str]]:
    if not per_file:
        raise ValueError("No per-file compare results to aggregate")

    first = next(iter(per_file.values()))
    duplicate_ids: list[str] = []
    seen: dict[str, str] = {}
    combined_rows: list[dict] = []

    for basename in sorted(per_file):
        for row in per_file[basename].changed_rows:
            tid = str(row.get("id") or "")
            if tid in seen:
                if tid not in duplicate_ids:
                    duplicate_ids.append(tid)
                continue
            seen[tid] = basename
            enriched = dict(row)
            enriched["ndjson_source"] = basename
            combined_rows.append(enriched)

    return (
        AllowlistCompareResult(
            total=sum(r.total for r in per_file.values()),
            tbc_old=sum(r.tbc_old for r in per_file.values()),
            tbc_new=sum(r.tbc_new for r in per_file.values()),
            changed_rows=combined_rows,
            zero_candidate_old=sum(r.zero_candidate_old for r in per_file.values()),
            zero_candidate_new=sum(r.zero_candidate_new for r in per_file.values()),
            allowlist_old_size=first.allowlist_old_size,
            allowlist_new_size=first.allowlist_new_size,
            tuples_merged=len(selected_tuples),
            tbc_b2b_old=sum(r.tbc_b2b_old for r in per_file.values()),
            tbc_b2b_new=sum(r.tbc_b2b_new for r in per_file.values()),
            tbc_b2c_old=sum(r.tbc_b2c_old for r in per_file.values()),
            tbc_b2c_new=sum(r.tbc_b2c_new for r in per_file.values()),
            margin_loss_old=sum(r.margin_loss_old for r in per_file.values()),
            margin_loss_new=sum(r.margin_loss_new for r in per_file.values()),
            below_threshold_old=sum(r.below_threshold_old for r in per_file.values()),
            below_threshold_new=sum(r.below_threshold_new for r in per_file.values()),
            rules_targeting_selected_old=first.rules_targeting_selected_old,
            rules_targeting_selected_new=first.rules_targeting_selected_new,
        ),
        duplicate_ids,
    )


def _outcome_counts(changed_rows: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    counts = {"gap_fix": 0, "regression": 0, "reroute": 0}
    mechanisms = {"allowlist_gap": 0, "scoring_recovery": 0}
    for row in changed_rows:
        outcome = row.get("outcome_type")
        if outcome in counts:
            counts[outcome] += 1
        mech = row.get("gap_fix_mechanism")
        if mech in mechanisms:
            mechanisms[mech] += 1
    return counts, mechanisms


def _is_tuple_no_op(
    ndjson_paths: list[Path],
    allow_old: AllowList,
    tup: FiveTuple,
    *,
    limit: int | None,
    enrich_changed_rows: bool,
) -> bool:
    allow_new = AllowList(tuples=frozenset(allow_old.tuples | {tup}))
    tbc_delta = 0
    any_changed = False
    for path in ndjson_paths:
        result = compare_allowlists_on_ndjson(
            path,
            allow_old,
            allow_new,
            limit=limit,
            enrich_changed_rows=enrich_changed_rows,
        )
        tbc_delta += result.tbc_old - result.tbc_new
        if result.changed_rows:
            any_changed = True
    return tbc_delta == 0 and not any_changed


def compute_selection_no_op_count(
    ndjson_paths: list[Path],
    allow_old: AllowList,
    selected: frozenset[FiveTuple],
    *,
    limit: int | None = None,
    enrich_changed_rows: bool = False,
) -> int:
    return sum(
        1
        for t in selected
        if _is_tuple_no_op(
            ndjson_paths,
            allow_old,
            t,
            limit=limit,
            enrich_changed_rows=enrich_changed_rows,
        )
    )


def classify_verdict_band(
    result: BatchCompareResult,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    combined = result.combined
    net_tbc = combined.tbc_old - combined.tbc_new
    n_selected = len(result.selected_tuples)

    if result.selection_no_op_count is not None and n_selected:
        rate = result.selection_no_op_count / n_selected
        if rate >= 0.5:
            reasons.append(f"selection_no_op_rate={rate:.2f}>=0.5")
            return "rules_needed", reasons

    if n_selected and result.tuples_with_rules_count < n_selected * 0.5:
        reasons.append(
            f"tuples_with_rules_count={result.tuples_with_rules_count}<{n_selected * 0.5:.1f}"
        )
        return "rules_needed", reasons

    if (
        net_tbc < 0
        and combined.zero_candidate_new == combined.zero_candidate_old
        and combined.margin_loss_new > combined.margin_loss_old
    ):
        reasons.append("net_tbc_regression_with_margin_loss_increase")
        return "risky", reasons

    gap_fix = result.outcome_counts.get("gap_fix", 0)
    regression = result.outcome_counts.get("regression", 0)
    if net_tbc > 0 and gap_fix > 0 and regression <= gap_fix:
        reasons.append("net_tbc_improved_with_gap_fixes")
        return "strong_commit", reasons

    reasons.append("default_review")
    return "review", reasons


def run_commit_simulation(
    ndjson_paths: list[Path],
    allow_old: AllowList,
    allow_new: AllowList,
    *,
    selected_tuples: frozenset[FiveTuple],
    rule_specs_new: tuple[RuleSpec, ...] | None = None,
    limit: int | None = None,
    enrich_changed_rows: bool = True,
    compute_no_op: bool = False,
) -> BatchCompareResult:
    allowlist_old_size = len(allow_old.tuples)
    allowlist_new_size = len(allow_new.tuples)
    tuples_merged = len(selected_tuples)

    per_file: dict[str, AllowlistCompareResult] = {}
    for path in sorted(ndjson_paths):
        per_file[path.name] = compare_allowlists_on_ndjson(
            path,
            allow_old,
            allow_new,
            limit=limit,
            allowlist_old_size=allowlist_old_size,
            allowlist_new_size=allowlist_new_size,
            tuples_merged=tuples_merged,
            rule_specs_new=rule_specs_new,
            selected_tuples=selected_tuples,
            enrich_changed_rows=enrich_changed_rows,
        )

    combined, duplicate_ids = _sum_compare_results(per_file, selected_tuples=selected_tuples)
    outcome_counts, gap_fix_by_mechanism = _outcome_counts(combined.changed_rows)
    tuples_with_rules = count_tuples_with_rules(
        selected_tuples,
        rule_specs_new=rule_specs_new,
    )
    selection_no_op_count = (
        compute_selection_no_op_count(
            ndjson_paths,
            allow_old,
            selected_tuples,
            limit=limit,
            enrich_changed_rows=enrich_changed_rows,
        )
        if compute_no_op
        else None
    )

    partial = BatchCompareResult(
        per_file=per_file,
        combined=combined,
        selected_tuples=selected_tuples,
        outcome_counts=outcome_counts,
        gap_fix_by_mechanism=gap_fix_by_mechanism,
        tuples_with_rules_count=tuples_with_rules,
        selection_no_op_count=selection_no_op_count,
        duplicate_ticket_ids=duplicate_ids,
        verdict_band="review",
        verdict_reasons=[],
    )
    band, reasons = classify_verdict_band(partial)
    return BatchCompareResult(
        per_file=per_file,
        combined=combined,
        selected_tuples=selected_tuples,
        outcome_counts=outcome_counts,
        gap_fix_by_mechanism=gap_fix_by_mechanism,
        tuples_with_rules_count=tuples_with_rules,
        selection_no_op_count=selection_no_op_count,
        duplicate_ticket_ids=duplicate_ids,
        verdict_band=band,
        verdict_reasons=reasons,
    )


def build_old_classification_cache(
    ndjson_paths: list[Path],
    allow_old: AllowList,
    *,
    limit: int | None = None,
    rule_specs_old: tuple[RuleSpec, ...] | None = None,
) -> OldCache:
    specs = rule_specs_old if rule_specs_old is not None else load_rule_specs()
    cache: OldCache = {}
    for path in sorted(ndjson_paths):
        entries: list[tuple[dict, Any]] = []
        thread_index = (
            build_ticket_index(_iter_ticket_dicts(path))
            if thread_enrichment_enabled()
            else {}
        )
        for ticket in _iter_ticket_dicts(path):
            if limit is not None and len(entries) >= limit:
                break
            row = flatten_for_classify(ticket, thread_index)
            old_dec = classify_row_with_explanation(row, allow_old, rule_specs=specs)
            entries.append((row, old_dec))
        cache[path.name] = entries
    return cache


def _tuple_has_rule(
    tup: FiveTuple,
    *,
    rule_specs: tuple[RuleSpec, ...] | None = None,
) -> bool:
    rules = rule_specs if rule_specs is not None else load_rule_specs()
    return has_rule_target(tup, json_rules=rules, computed_targets=computed_rule_targets())


def _ablate_one_tuple(
    cache: OldCache,
    allow_old: AllowList,
    tup: FiveTuple,
    *,
    rule_specs_new: tuple[RuleSpec, ...] | None = None,
    rule_specs_old: tuple[RuleSpec, ...] | None = None,
    enrich_changed_rows: bool = True,
) -> TupleAblationResult:
    specs_old = rule_specs_old if rule_specs_old is not None else load_rule_specs()
    specs_new = rule_specs_new if rule_specs_new is not None else specs_old
    allow_new = AllowList(tuples=frozenset(allow_old.tuples | {tup}))

    tbc_old = 0
    tbc_new = 0
    gap_fix = 0
    regression = 0
    reroute = 0
    changed_rows: list[dict] = []

    for _basename, entries in sorted(cache.items()):
        for row, old_dec in entries:
            if _is_tbc(old_dec):
                tbc_old += 1
            new_dec = classify_row_with_explanation(row, allow_new, rule_specs=specs_new)
            if _is_tbc(new_dec):
                tbc_new += 1
            if old_dec.tier != new_dec.tier:
                row_data = {
                    "id": str(row.get("id") or ""),
                    "old_tier4": old_dec.tier[3],
                    "new_tier4": new_dec.tier[3],
                    "old_tuple": old_dec.tier,
                    "new_tuple": new_dec.tier,
                }
                if enrich_changed_rows:
                    row_data.update(enrich_changed_row(old_dec, new_dec))
                    outcome = row_data.get("outcome_type")
                    if outcome == "gap_fix":
                        gap_fix += 1
                    elif outcome == "regression":
                        regression += 1
                    elif outcome == "reroute":
                        reroute += 1
                changed_rows.append(row_data)

    tbc_delta = tbc_old - tbc_new
    return TupleAblationResult(
        five_tuple=tup,
        tbc_delta=tbc_delta,
        gap_fix_count=gap_fix,
        regression_count=regression,
        reroute_count=reroute,
        no_op=tbc_delta == 0 and not changed_rows,
        has_rule=_tuple_has_rule(tup, rule_specs=specs_new),
        segment=tup[0],
        stream=tup[1],
        cat=tup[2],
    )


def run_tuple_ablation(
    ndjson_paths: list[Path],
    allow_old: AllowList,
    selected: frozenset[FiveTuple],
    *,
    rule_specs_builder: Callable[[FiveTuple], tuple[RuleSpec, ...] | None] | None = None,
    limit: int | None = None,
    ablation_limit: int | None = None,
    enrich_changed_rows: bool = True,
    cache_old_classifications: bool = True,
) -> list[TupleAblationResult]:
    tuples_to_run = sorted(selected)
    if ablation_limit is not None:
        tuples_to_run = tuples_to_run[:ablation_limit]

    cache: OldCache | None = None
    if cache_old_classifications:
        cache = build_old_classification_cache(
            ndjson_paths,
            allow_old,
            limit=limit,
        )

    results: list[TupleAblationResult] = []
    for tup in tuples_to_run:
        rule_specs_new = rule_specs_builder(tup) if rule_specs_builder else None
        if cache is not None:
            results.append(
                _ablate_one_tuple(
                    cache,
                    allow_old,
                    tup,
                    rule_specs_new=rule_specs_new,
                    enrich_changed_rows=enrich_changed_rows,
                )
            )
        else:
            allow_new = AllowList(tuples=frozenset(allow_old.tuples | {tup}))
            per_tuple: list[TupleAblationResult] = []
            for path in ndjson_paths:
                cmp = compare_allowlists_on_ndjson(
                    path,
                    allow_old,
                    allow_new,
                    limit=limit,
                    rule_specs_new=rule_specs_new,
                    enrich_changed_rows=enrich_changed_rows,
                )
                per_tuple.append(
                    TupleAblationResult(
                        five_tuple=tup,
                        tbc_delta=cmp.tbc_old - cmp.tbc_new,
                        gap_fix_count=sum(
                            1 for r in cmp.changed_rows if r.get("outcome_type") == "gap_fix"
                        ),
                        regression_count=sum(
                            1 for r in cmp.changed_rows if r.get("outcome_type") == "regression"
                        ),
                        reroute_count=sum(
                            1 for r in cmp.changed_rows if r.get("outcome_type") == "reroute"
                        ),
                        no_op=(cmp.tbc_old - cmp.tbc_new) == 0 and not cmp.changed_rows,
                        has_rule=_tuple_has_rule(tup, rule_specs=rule_specs_new),
                        segment=tup[0],
                        stream=tup[1],
                        cat=tup[2],
                    )
                )
            if per_tuple:
                total_delta = sum(r.tbc_delta for r in per_tuple)
                total_changed = sum(
                    r.gap_fix_count + r.regression_count + r.reroute_count for r in per_tuple
                )
                results.append(
                    TupleAblationResult(
                        five_tuple=tup,
                        tbc_delta=total_delta,
                        gap_fix_count=sum(r.gap_fix_count for r in per_tuple),
                        regression_count=sum(r.regression_count for r in per_tuple),
                        reroute_count=sum(r.reroute_count for r in per_tuple),
                        no_op=total_delta == 0 and total_changed == 0,
                        has_rule=per_tuple[0].has_rule,
                        segment=tup[0],
                        stream=tup[1],
                        cat=tup[2],
                    )
                )
    return results


def apply_ablation_no_op_to_result(
    result: BatchCompareResult,
    ablation: list[TupleAblationResult],
) -> BatchCompareResult:
    no_op_count = sum(1 for row in ablation if row.no_op)
    partial = BatchCompareResult(
        per_file=result.per_file,
        combined=result.combined,
        selected_tuples=result.selected_tuples,
        outcome_counts=result.outcome_counts,
        gap_fix_by_mechanism=result.gap_fix_by_mechanism,
        tuples_with_rules_count=result.tuples_with_rules_count,
        selection_no_op_count=no_op_count,
        duplicate_ticket_ids=result.duplicate_ticket_ids,
        verdict_band=result.verdict_band,
        verdict_reasons=result.verdict_reasons,
    )
    band, reasons = classify_verdict_band(partial)
    return BatchCompareResult(
        per_file=result.per_file,
        combined=result.combined,
        selected_tuples=result.selected_tuples,
        outcome_counts=result.outcome_counts,
        gap_fix_by_mechanism=result.gap_fix_by_mechanism,
        tuples_with_rules_count=result.tuples_with_rules_count,
        selection_no_op_count=no_op_count,
        duplicate_ticket_ids=result.duplicate_ticket_ids,
        verdict_band=band,
        verdict_reasons=reasons,
    )


def _serialize_tuple(t: FiveTuple) -> list[str]:
    return list(t)


def _serialize_changed_row(row: dict) -> dict:
    out: dict[str, Any] = {}
    for key, val in row.items():
        if key in ("old_tuple", "new_tuple") and isinstance(val, tuple):
            out[key] = _serialize_tuple(val)
        else:
            out[key] = val
    return out


def compare_result_to_dict(result: AllowlistCompareResult) -> dict[str, Any]:
    data = asdict(result)
    data["changed_rows"] = [_serialize_changed_row(r) for r in result.changed_rows]
    return data


def write_batch_reports(result: BatchCompareResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    combined = result.combined
    n_selected = len(result.selected_tuples)

    verdict: dict[str, Any] = {
        "schema_version": 1,
        "combined_is_synthetic": True,
        "counter_aggregation": "summed_per_file",
        "changed_rows_aggregation": "deduped_by_ticket_id_first_file_wins",
        "verdict_band": result.verdict_band,
        "verdict_reasons": result.verdict_reasons,
        "duplicate_ticket_ids": result.duplicate_ticket_ids,
        "selected_tuple_count": n_selected,
        "tuples_with_rules_count": result.tuples_with_rules_count,
        "selection_no_op_count": result.selection_no_op_count,
        "selection_no_op_rate": (
            result.selection_no_op_count / n_selected if result.selection_no_op_count is not None and n_selected else None
        ),
        "net_tbc_improvement": combined.tbc_old - combined.tbc_new,
        "outcome_counts": result.outcome_counts,
        "gap_fix_by_mechanism": result.gap_fix_by_mechanism,
        "combined": compare_result_to_dict(combined),
        "per_file_summary": {
            name: {
                "total": r.total,
                "tbc_old": r.tbc_old,
                "tbc_new": r.tbc_new,
                "tbc_delta": r.tbc_new - r.tbc_old,
                "zero_candidate_old": r.zero_candidate_old,
                "zero_candidate_new": r.zero_candidate_new,
                "changed_row_count": len(r.changed_rows),
            }
            for name, r in result.per_file.items()
        },
    }
    (output_dir / "commit_verdict.json").write_text(
        json.dumps(verdict, indent=2),
        encoding="utf-8",
    )

    per_file_payload = {name: compare_result_to_dict(r) for name, r in result.per_file.items()}
    (output_dir / "per_file.json").write_text(
        json.dumps(per_file_payload, indent=2),
        encoding="utf-8",
    )

    if combined.changed_rows:
        fieldnames: list[str] = []
        for row in combined.changed_rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
        with (output_dir / "changed_rows.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in combined.changed_rows:
                csv_row = dict(row)
                for key in ("old_tuple", "new_tuple"):
                    if key in csv_row and isinstance(csv_row[key], tuple):
                        csv_row[key] = "|".join(csv_row[key])
                writer.writerow(csv_row)


def write_ablation_reports(ablation: list[TupleAblationResult], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tuple_fields = [
        "tuple",
        "tbc_delta",
        "gap_fix_count",
        "regression_count",
        "reroute_count",
        "no_op",
        "has_rule",
        "segment",
        "stream",
        "cat",
    ]
    with (output_dir / "tuple_risk.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=tuple_fields)
        writer.writeheader()
        for row in ablation:
            writer.writerow(
                {
                    "tuple": "|".join(row.five_tuple),
                    "tbc_delta": row.tbc_delta,
                    "gap_fix_count": row.gap_fix_count,
                    "regression_count": row.regression_count,
                    "reroute_count": row.reroute_count,
                    "no_op": row.no_op,
                    "has_rule": row.has_rule,
                    "segment": row.segment,
                    "stream": row.stream,
                    "cat": row.cat,
                }
            )

    rollup: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
        lambda: {
            "tuple_count": 0,
            "tbc_delta": 0,
            "gap_fix_count": 0,
            "regression_count": 0,
            "reroute_count": 0,
            "no_op_count": 0,
        }
    )
    for row in ablation:
        key = (row.segment, row.stream, row.cat)
        bucket = rollup[key]
        bucket["tuple_count"] += 1
        bucket["tbc_delta"] += row.tbc_delta
        bucket["gap_fix_count"] += row.gap_fix_count
        bucket["regression_count"] += row.regression_count
        bucket["reroute_count"] += row.reroute_count
        if row.no_op:
            bucket["no_op_count"] += 1

    pattern_fields = [
        "segment",
        "stream",
        "cat",
        "tuple_count",
        "tbc_delta",
        "gap_fix_count",
        "regression_count",
        "reroute_count",
        "no_op_count",
    ]
    with (output_dir / "pattern_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=pattern_fields)
        writer.writeheader()
        for (segment, stream, cat), metrics in sorted(rollup.items()):
                writer.writerow(
                {
                    "segment": segment,
                    "stream": stream,
                    "cat": cat,
                    **metrics,
                }
            )


def _format_tuple(t: FiveTuple | tuple[str, ...]) -> str:
    return "|".join(t)


def _format_tuple_human(t: FiveTuple | tuple[str, ...]) -> str:
    return " / ".join(t)


def _format_delta(value: int) -> str:
    if value > 0:
        return f"+{value}"
    return str(value)


def _build_interpretation_lines(
    result: BatchCompareResult,
    combined: AllowlistCompareResult,
    *,
    net_tbc: int,
    no_op_rate: float | None,
    n_selected: int,
    ablation: list[TupleAblationResult] | None,
) -> list[str]:
    lines: list[str] = ["## Interpretation", ""]
    gap_fix = result.outcome_counts.get("gap_fix", 0)
    regression = result.outcome_counts.get("regression", 0)
    allowlist_gap = result.gap_fix_by_mechanism.get("allowlist_gap", 0)
    scoring_recovery = result.gap_fix_by_mechanism.get("scoring_recovery", 0)
    zero_flat = combined.zero_candidate_old == combined.zero_candidate_new

    if result.verdict_band == "rules_needed":
        if no_op_rate is not None and no_op_rate >= 0.5:
            moved = gap_fix + regression + result.outcome_counts.get("reroute", 0)
            lines.append(
                f"The **`rules_needed`** verdict reflects a high no-op rate ({no_op_rate * 100:.0f}%): "
                f"adding {n_selected} allow-list tuples (with rules on {result.tuples_with_rules_count}) "
                f"only moved {moved} ticket(s) on this export. Most of the selection is inert on this batch."
            )
        else:
            lines.append(
                f"The **`rules_needed`** verdict indicates rule coverage gaps: fewer than half of selected "
                f"tuples ({result.tuples_with_rules_count}/{n_selected}) have matching rules."
            )
    elif result.verdict_band == "strong_commit":
        lines.append(
            f"The **`strong_commit`** verdict indicates a net TBC improvement of {_format_delta(net_tbc)} "
            f"with {gap_fix} gap fix(es) and no more regressions than fixes."
        )
    elif result.verdict_band == "risky":
        lines.append(
            "The **`risky`** verdict flags net TBC regression alongside increased margin-loss TBC — "
            "review changed tickets before committing."
        )
    else:
        lines.append(
            f"The **`review`** verdict means results are mixed or inconclusive — "
            f"net TBC {_format_delta(net_tbc)}, {gap_fix} gap fix(es), {regression} regression(s)."
        )

    if gap_fix > 0:
        lines.append("")
        if allowlist_gap == 0 and scoring_recovery > 0:
            if gap_fix == 1:
                lines.append(
                    "The single gap fix is a **scoring recovery**, not an allow-list gap "
                    f"(`allowlist_gap: 0`, `scoring_recovery: {scoring_recovery}`)."
                )
            else:
                lines.append(
                    f"All {gap_fix} gap fixes are **scoring recoveries**, not allow-list gaps "
                    f"(`allowlist_gap: 0`, `scoring_recovery: {scoring_recovery}`)."
                )
        elif allowlist_gap > 0 and scoring_recovery > 0:
            lines.append(
                f"Gap fixes split between **allow-list gaps** ({allowlist_gap}) and "
                f"**scoring recoveries** ({scoring_recovery})."
            )
        elif allowlist_gap > 0:
            lines.append(
                f"All {gap_fix} gap fix(es) close **allow-list gaps** — tickets that previously had zero candidates."
            )

    if zero_flat and gap_fix > 0:
        lines.append("")
        lines.append(
            f"`zero_candidate` tickets are unchanged ({combined.zero_candidate_old}) — "
            "benefit comes from scoring/rule routing, not from closing allow-list gaps."
        )
    elif not zero_flat and combined.zero_candidate_new < combined.zero_candidate_old:
        delta = combined.zero_candidate_old - combined.zero_candidate_new
        lines.append("")
        lines.append(
            f"`zero_candidate` tickets dropped by {delta} "
            f"({combined.zero_candidate_old} → {combined.zero_candidate_new}) — "
            "allow-list expansion is closing real coverage gaps."
        )

    b2b_delta = combined.tbc_b2b_old - combined.tbc_b2b_new
    b2c_delta = combined.tbc_b2c_old - combined.tbc_b2c_new
    if b2b_delta != 0 or b2c_delta != 0:
        lines.append("")
        parts: list[str] = []
        if b2b_delta != 0:
            parts.append(f"B2B TBC {combined.tbc_b2b_old} → {combined.tbc_b2b_new} ({_format_delta(b2b_delta)})")
        if b2c_delta != 0:
            parts.append(f"B2C TBC {combined.tbc_b2c_old} → {combined.tbc_b2c_new} ({_format_delta(b2c_delta)})")
        lines.append("")
        lines.append(f"**Segment impact:** {'; '.join(parts)}.")

    margin_delta = combined.margin_loss_new - combined.margin_loss_old
    if margin_delta > 0:
        lines.append("")
        lines.append(
            f"Margin-loss TBC rose ({combined.margin_loss_old} → {combined.margin_loss_new}) — "
            "some tickets lost classification confidence after the commit."
        )

    if regression > 0:
        lines.append("")
        if net_tbc <= 0 and gap_fix > 0:
            lines.append(
                f"On this export, the full {n_selected}-tuple commit is **net neutral or negative** on TBC: "
                f"{gap_fix} fix(es) offset by {regression} regression(s)."
            )
        else:
            lines.append(
                f"{regression} regression(s) detected — review affected tuples before committing the full selection."
            )

    if ablation is not None:
        active = [row for row in ablation if not row.no_op]
        helpful = [row for row in active if row.tbc_delta > 0]
        harmful = [row for row in active if row.tbc_delta < 0]
        if len(active) == 1 and len(ablation) > 1:
            row = active[0]
            lines.append("")
            lines.append(
                f"Ablation shows benefit is concentrated in one tuple: "
                f"`{_format_tuple_human(row.five_tuple)}` ({_format_delta(row.tbc_delta)} TBC)."
            )
        elif helpful and not harmful:
            lines.append("")
            lines.append(
                f"Ablation: {len(helpful)} helpful tuple(s), no harmful tuples on this export."
            )
        elif helpful and harmful:
            lines.append("")
            lines.append(
                f"Ablation: {len(helpful)} helpful and {len(harmful)} harmful tuple(s) — "
                "consider dropping harmful tuples or validating across additional exports."
            )
            for row in harmful:
                lines.append(
                    f"- `{_format_tuple_human(row.five_tuple)}` — "
                    f"{_format_delta(row.tbc_delta)} TBC, {row.regression_count} regression(s)"
                )

    if (
        result.verdict_band in ("rules_needed", "review")
        and no_op_rate is not None
        and no_op_rate >= 0.5
        and n_selected > 1
    ):
        lines.append("")
        lines.append(
            "Before committing the full selection, consider narrowing to tuples with demonstrated impact "
            "or validating on additional NDJSON exports where more of these categories appear."
        )
    elif result.verdict_band == "strong_commit" and regression == 0:
        lines.append("")
        lines.append(
            "Results support committing this selection on the evidence of this export; "
            "still validate on additional batches if ticket volume here is low."
        )

    return lines


def write_summary_markdown(
    result: BatchCompareResult,
    output_dir: Path,
    *,
    ablation: list[TupleAblationResult] | None = None,
    ndjson_paths: list[Path] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    combined = result.combined
    n_selected = len(result.selected_tuples)
    net_tbc = combined.tbc_old - combined.tbc_new
    no_op_rate = (
        result.selection_no_op_count / n_selected
        if result.selection_no_op_count is not None and n_selected
        else None
    )

    lines: list[str] = [
        "# Batch Allow-List Impact Summary",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    ndjson_names = [p.name for p in ndjson_paths] if ndjson_paths else []
    if ndjson_names:
        export_label = ", ".join(f"`{name}`" for name in ndjson_names)
        lines.append(
            f"Full View A + B analysis on **{combined.total} tickets** from {export_label}. "
            f"Candidate commit adds **{n_selected} novel tuples** "
            f"({result.tuples_with_rules_count} with generated rules)."
        )
    else:
        lines.append(
            f"Full View A + B analysis on **{combined.total} tickets**. "
            f"Candidate commit adds **{n_selected} novel tuples**."
        )
    lines.extend(["", "## Inputs", ""])
    if ndjson_paths:
        for path in ndjson_paths:
            lines.append(f"- NDJSON: `{path}`")
    else:
        lines.append("- NDJSON: (not recorded)")
    lines.extend(
        [
            f"- Selected tuples: {n_selected} (all novel from upload)",
            f"- Tuples with rules: {result.tuples_with_rules_count} / {n_selected}",
            f"- Tickets analysed: {combined.total}",
            "",
            "## View A — Commit Verdict",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Verdict band | `{result.verdict_band}` |",
            f"| Net TBC improvement | **{_format_delta(net_tbc)}** ({combined.tbc_old} → {combined.tbc_new}) |",
            f"| Gap fixes | {result.outcome_counts.get('gap_fix', 0)} |",
            f"| Regressions | {result.outcome_counts.get('regression', 0)} |",
            f"| Reroutes | {result.outcome_counts.get('reroute', 0)} |",
            f"| Allow-list size | {combined.allowlist_old_size} → {combined.allowlist_new_size} (+{n_selected}) |",
            f"| Zero-candidate tickets | {combined.zero_candidate_old} → {combined.zero_candidate_new} |",
            f"| B2B TBC | {combined.tbc_b2b_old} → {combined.tbc_b2b_new} |",
            f"| B2C TBC | {combined.tbc_b2c_old} → {combined.tbc_b2c_new} |",
            f"| Margin-loss TBC | {combined.margin_loss_old} → {combined.margin_loss_new} |",
        ]
    )
    if result.selection_no_op_count is not None:
        rate_pct = f"{no_op_rate * 100:.0f}%" if no_op_rate is not None else "n/a"
        lines.append(f"| Selection no-op rate | {rate_pct} ({result.selection_no_op_count}/{n_selected}) |")

    if result.verdict_reasons:
        lines.extend(["", "**Verdict reasons:**"])
        lines.extend(f"- `{reason}`" for reason in result.verdict_reasons)

    allowlist_gap = result.gap_fix_by_mechanism.get("allowlist_gap", 0)
    scoring_recovery = result.gap_fix_by_mechanism.get("scoring_recovery", 0)
    gap_fix = result.outcome_counts.get("gap_fix", 0)
    lines.extend(["", "### Gap-fix mechanism", ""])
    if gap_fix == 0:
        lines.append("_No gap fixes on this export._")
    elif allowlist_gap == 0 and scoring_recovery > 0:
        lines.append(
            f"All {gap_fix} fix(es) are **scoring recoveries**, not allow-list gaps "
            f"(`allowlist_gap: 0`, `scoring_recovery: {scoring_recovery}`)."
        )
    else:
        lines.append(f"- allowlist_gap: {allowlist_gap}")
        lines.append(f"- scoring_recovery: {scoring_recovery}")

    if result.duplicate_ticket_ids:
        lines.extend(
            [
                "",
                f"**Warning:** {len(result.duplicate_ticket_ids)} duplicate ticket ID(s) across exports.",
            ]
        )

    changed = combined.changed_rows
    lines.extend(["", f"### Changed tickets ({len(changed)})", ""])
    if changed:
        for i, row in enumerate(changed, start=1):
            old_t = row["old_tuple"] if isinstance(row.get("old_tuple"), tuple) else ()
            new_t = row["new_tuple"] if isinstance(row.get("new_tuple"), tuple) else ()
            outcome = row.get("outcome_type", "")
            mechanism = row.get("gap_fix_mechanism")
            tbc_note = ""
            if row.get("old_tbc") and not row.get("new_tbc"):
                tbc_note = " (TBC cleared)"
            elif not row.get("old_tbc") and row.get("new_tbc"):
                reason = row.get("new_tbc_reason") or "TBC"
                tbc_note = f" (new TBC: {reason})"
            detail = f" — {mechanism}" if mechanism else ""
            lines.append(
                f"{i}. **{row.get('id')}** ({outcome}{detail}){tbc_note}: "
                f"`{_format_tuple_human(old_t)}` → `{_format_tuple_human(new_t)}`"
            )
    else:
        lines.append("_No ticket-level changes on this export._")

    if ablation is not None:
        active = [row for row in ablation if not row.no_op]
        regressions = [row for row in ablation if row.regression_count > 0]
        no_ops = [row for row in ablation if row.no_op]
        lines.extend(
            [
                "",
                "## View B — Tuple Risk (ablation)",
                "",
                f"**{len(no_ops)} of {len(ablation)} tuples are no-ops** on this export "
                f"(`no_op=True`, `tbc_delta=0`).",
                "",
            ]
        )
        if active:
            lines.extend(["**Tuples with impact:**", ""])
            lines.append("| Tuple | tbc_delta | gap_fix | regression | has_rule |")
            lines.append("|-------|-----------|---------|------------|----------|")
            for row in sorted(active, key=lambda r: -r.tbc_delta):
                lines.append(
                    f"| `{_format_tuple_human(row.five_tuple)}` | {_format_delta(row.tbc_delta)} | "
                    f"{row.gap_fix_count} | {row.regression_count} | {row.has_rule} |"
                )
        else:
            lines.append("_No tuple produced ticket-level movement on this export._")

        if regressions:
            lines.extend(["", "**Regression tuples:**", ""])
            for row in regressions:
                lines.append(
                    f"- `{_format_tuple_human(row.five_tuple)}` — "
                    f"tbc_delta {_format_delta(row.tbc_delta)}, {row.regression_count} regression(s)"
                )

        pattern_hotspots: dict[tuple[str, str, str], dict[str, int]] = defaultdict(
            lambda: {"tbc_delta": 0, "tuple_count": 0, "no_op_count": 0}
        )
        for row in ablation:
            key = (row.segment, row.stream, row.cat)
            bucket = pattern_hotspots[key]
            bucket["tuple_count"] += 1
            bucket["tbc_delta"] += row.tbc_delta
            if row.no_op:
                bucket["no_op_count"] += 1
        active_patterns = {
            key: metrics for key, metrics in pattern_hotspots.items() if metrics["tbc_delta"] != 0
        }
        if active_patterns:
            lines.extend(["", "**Pattern hotspots:**", ""])
            for (segment, stream, cat), metrics in sorted(
                active_patterns.items(), key=lambda item: -abs(item[1]["tbc_delta"])
            ):
                lines.append(
                    f"- `({segment}, {stream}, {cat})` — net {_format_delta(metrics['tbc_delta'])} TBC, "
                    f"{metrics['tuple_count']} tuple(s), {metrics['no_op_count']} no-op(s)"
                )

    lines.append("")
    lines.extend(
        _build_interpretation_lines(
            result,
            combined,
            net_tbc=net_tbc,
            no_op_rate=no_op_rate,
            n_selected=n_selected,
            ablation=ablation,
        )
    )

    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
