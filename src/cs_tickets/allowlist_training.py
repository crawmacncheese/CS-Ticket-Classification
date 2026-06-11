from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from cs_tickets.allowlist_compare import AllowlistCompareResult
from cs_tickets.classifier_rules import RuleSpec, load_rule_specs, reload_rule_specs
from cs_tickets.rule_coverage import computed_rule_targets, has_rule_target, rule_target_tiers
from cs_tickets.rule_generator import GeneratedRule, generate_rule_from_exemplar, upsert_training_rules
from cs_tickets.taxonomy import (
    AllowList,
    count_classified_tickets_per_tuple,
    diff_against_allowlist,
    extract_classified_workbook_five_tuples,
    load_allowlist,
    merge_tuples_into_workbook,
    resolve_exemplars_for_tuples,
)

_MAX_SNAPSHOTS = 5
_TRAINING_SESSIONS: dict[str, _TrainingSession] = {}


@dataclass(frozen=True)
class CommitResult:
    rows_added: int
    rules_added: int
    rules_skipped: int


@dataclass
class _TrainingSession:
    session_id: str
    temp_dir: Path
    upload_path: Path
    upload_tuples: frozenset[tuple[str, str, str, str, str]]
    new_tuples: frozenset[tuple[str, str, str, str, str]]
    selected_tuples: frozenset[tuple[str, str, str, str, str]] = field(default_factory=frozenset)
    ticket_counts: dict[tuple[str, str, str, str, str], int] = field(default_factory=dict)
    preview_result: AllowlistCompareResult | None = None
    preview_selection_hash: str | None = None
    preview_bad_satisfaction_only: bool = False
    repo_root: Path = field(default_factory=Path.cwd)


def training_available(repo_root: Path) -> bool:
    doc = repo_root / "doc"
    wb = doc / "CS_ticket_new_categorizations.xlsx"
    return doc.is_dir() and os.access(doc, os.W_OK) and wb.is_file() and os.access(wb, os.W_OK)


def selection_hash(selected: frozenset[tuple[str, str, str, str, str]]) -> str:
    payload = "|".join("|".join(t) for t in sorted(selected))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _doc_paths(repo_root: Path) -> tuple[Path, Path, Path | None]:
    doc = repo_root / "doc"
    wb = doc / "CS_ticket_new_categorizations.xlsx"
    tax = doc / "Taxonomy.csv"
    return doc, wb, tax if tax.is_file() else None


def _training_rules_path(repo_root: Path) -> Path:
    return repo_root / "doc" / "training_rules.json"


def create_session(upload_xlsx: Path, repo_root: Path) -> _TrainingSession:
    for old in list(_TRAINING_SESSIONS.values()):
        drop_session(old)
    _TRAINING_SESSIONS.clear()

    temp_dir = Path(tempfile.mkdtemp(prefix="cs_training_"))
    dest = temp_dir / "upload.xlsx"
    shutil.copy2(upload_xlsx, dest)

    _, wb_path, tax_path = _doc_paths(repo_root)
    allow = load_allowlist(tax_path, wb_path)
    upload_tuples = extract_classified_workbook_five_tuples(dest)
    new_tuples = diff_against_allowlist(upload_tuples, allow)
    counts = count_classified_tickets_per_tuple(dest)

    session_id = str(uuid.uuid4())
    session = _TrainingSession(
        session_id=session_id,
        temp_dir=temp_dir,
        upload_path=dest,
        upload_tuples=upload_tuples,
        new_tuples=new_tuples,
        ticket_counts=counts,
        repo_root=repo_root,
    )
    _TRAINING_SESSIONS[session_id] = session
    return session


def get_session(session_id: str) -> _TrainingSession | None:
    return _TRAINING_SESSIONS.get(session_id)


def build_candidate_allowlist(
    session: _TrainingSession,
    selected: frozenset[tuple[str, str, str, str, str]],
) -> tuple[AllowList, int]:
    _, wb_path, tax_path = _doc_paths(session.repo_root)
    candidate_wb = session.temp_dir / "candidate_workbook.xlsx"
    shutil.copy2(wb_path, candidate_wb)
    merged = merge_tuples_into_workbook(candidate_wb, session.upload_path, selected)
    return load_allowlist(tax_path, candidate_wb), merged


def build_candidate_rule_set(
    session: _TrainingSession,
    selected: frozenset[tuple[str, str, str, str, str]],
) -> tuple[RuleSpec, ...]:
    """Core + in-memory generated rules for selected tuples that need routing."""
    rules = load_rule_specs()
    targets = rule_target_tiers(rules)
    computed = computed_rule_targets()
    exemplars = resolve_exemplars_for_tuples(session.upload_path, selected)
    extra: list[RuleSpec] = []
    for tup in sorted(selected):
        if has_rule_target(tup, json_rules=rules, computed_targets=computed):
            continue
        exemplar = exemplars.get(tup)
        if not exemplar:
            continue
        generated = generate_rule_from_exemplar(
            exemplar,
            tup,
            existing_targets=targets,
            existing_rules=rules,
        )
        if generated is not None:
            extra.append(generated.spec)
            targets = rule_target_tiers(rules + tuple(extra))
    return rules + tuple(extra)


def build_candidate_rule_set_from_upload(
    repo_root: Path,
    upload_path: Path,
    selected: frozenset[tuple[str, str, str, str, str]],
) -> tuple[RuleSpec, ...]:
    """Generate candidate rules without registering a portal Training session."""
    upload_tuples = extract_classified_workbook_five_tuples(upload_path)
    _, wb_path, tax_path = _doc_paths(repo_root)
    allow = load_allowlist(tax_path, wb_path)
    session = _TrainingSession(
        session_id="cli",
        temp_dir=upload_path.parent,
        upload_path=upload_path,
        upload_tuples=upload_tuples,
        new_tuples=diff_against_allowlist(upload_tuples, allow),
        repo_root=repo_root,
    )
    return build_candidate_rule_set(session, selected)


def snapshot_doc_artifacts(repo_root: Path) -> Path:
    doc, wb_path, tax_path = _doc_paths(repo_root)
    snap_root = doc / ".snapshots"
    snap_root.mkdir(parents=True, exist_ok=True)
    snap_dir = snap_root / str(uuid.uuid4())
    snap_dir.mkdir()
    shutil.copy2(wb_path, snap_dir / wb_path.name)
    if tax_path:
        shutil.copy2(tax_path, snap_dir / tax_path.name)
    rules_path = _training_rules_path(repo_root)
    snap_rules = snap_dir / "training_rules.json"
    if rules_path.is_file():
        shutil.copy2(rules_path, snap_rules)
    else:
        snap_rules.write_text("[]\n", encoding="utf-8")
    _prune_snapshots(snap_root)
    return snap_dir


def _prune_snapshots(snap_root: Path) -> None:
    dirs = sorted(
        (p for p in snap_root.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in dirs[_MAX_SNAPSHOTS:]:
        shutil.rmtree(old, ignore_errors=True)


def _rules_to_upsert(
    session: _TrainingSession,
    merged_tuples: frozenset[tuple[str, str, str, str, str]],
    exemplars: dict[tuple[str, str, str, str, str], dict[str, str]],
) -> tuple[list[GeneratedRule], int]:
    rules = load_rule_specs()
    targets = rule_target_tiers(rules)
    computed = computed_rule_targets()
    to_upsert: list[GeneratedRule] = []
    skipped = 0
    for tup in sorted(merged_tuples):
        if has_rule_target(tup, json_rules=rules, computed_targets=computed):
            skipped += 1
            continue
        exemplar = exemplars.get(tup)
        if not exemplar:
            skipped += 1
            continue
        generated = generate_rule_from_exemplar(
            exemplar,
            tup,
            existing_targets=targets,
            existing_rules=rules,
        )
        if generated is None:
            skipped += 1
            continue
        to_upsert.append(generated)
        targets = rule_target_tiers(rules + tuple(g.spec for g in to_upsert))
    return to_upsert, skipped


def commit_session(
    session: _TrainingSession,
    selected: frozenset[tuple[str, str, str, str, str]],
) -> CommitResult:
    _, wb_path, _ = _doc_paths(session.repo_root)
    snap_dir = snapshot_doc_artifacts(session.repo_root)
    exemplars = resolve_exemplars_for_tuples(session.upload_path, selected)
    merged_tuples = frozenset(exemplars.keys())
    rules_to_upsert, rules_skipped = _rules_to_upsert(session, merged_tuples, exemplars)

    rows_added = merge_tuples_into_workbook(wb_path, session.upload_path, selected)
    rules_skipped += len(selected) - len(merged_tuples)

    rules_path = _training_rules_path(session.repo_root)
    try:
        rules_added = upsert_training_rules(rules_path, rules_to_upsert)
    except Exception:
        revert_snapshot(snap_dir, session.repo_root)
        raise

    reload_rule_specs()
    drop_session(session)
    return CommitResult(
        rows_added=rows_added,
        rules_added=rules_added,
        rules_skipped=rules_skipped,
    )


def latest_snapshot_dir(repo_root: Path) -> Path | None:
    snap_root = repo_root / "doc" / ".snapshots"
    if not snap_root.is_dir():
        return None
    dirs = sorted(
        (p for p in snap_root.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return dirs[0] if dirs else None


def has_revertable_snapshot(repo_root: Path) -> bool:
    return latest_snapshot_dir(repo_root) is not None


def revert_latest_snapshot(repo_root: Path) -> bool:
    snap_dir = latest_snapshot_dir(repo_root)
    if not snap_dir:
        return False
    revert_snapshot(snap_dir, repo_root)
    return True


def revert_snapshot(snapshot_dir: Path, repo_root: Path) -> None:
    _, wb_path, tax_path = _doc_paths(repo_root)
    snap_wb = snapshot_dir / wb_path.name
    if snap_wb.is_file():
        shutil.copy2(snap_wb, wb_path)
    if tax_path:
        snap_tax = snapshot_dir / tax_path.name
        if snap_tax.is_file():
            shutil.copy2(snap_tax, tax_path)
    snap_rules = snapshot_dir / "training_rules.json"
    rules_path = _training_rules_path(repo_root)
    if snap_rules.is_file():
        shutil.copy2(snap_rules, rules_path)
    elif rules_path.is_file():
        rules_path.unlink()
    reload_rule_specs()


def drop_session(session: _TrainingSession) -> None:
    _TRAINING_SESSIONS.pop(session.session_id, None)
    shutil.rmtree(session.temp_dir, ignore_errors=True)


def store_preview(
    session: _TrainingSession,
    result: AllowlistCompareResult,
    selected: frozenset[tuple[str, str, str, str, str]],
    *,
    bad_satisfaction_only: bool = False,
) -> None:
    session.preview_result = result
    session.preview_selection_hash = selection_hash(selected)
    session.preview_bad_satisfaction_only = bad_satisfaction_only
    session.selected_tuples = selected


def preview_is_stale(session: _TrainingSession, selected: frozenset[tuple[str, str, str, str, str]]) -> bool:
    if session.preview_result is None or session.preview_selection_hash is None:
        return False
    return session.preview_selection_hash != selection_hash(selected)


def commit_success_message(result: CommitResult) -> str:
    parts = [
        f"Added {result.rows_added} categor{'y' if result.rows_added == 1 else 'ies'}",
        f"{result.rules_added} matching rule{'s' if result.rules_added != 1 else ''}",
    ]
    msg = " and ".join(parts) + " to doc/."
    if result.rules_skipped:
        msg += f" ({result.rules_skipped} skipped — already routable or no exemplar row)."
    return msg
