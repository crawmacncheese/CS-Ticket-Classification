from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from cs_tickets.classifier_rules import RuleSpec, _load_rules_file
from cs_tickets.feedback.models import RuleProposal, TaxonomyProposal
from cs_tickets.live_config import (
    CONFIG_VERSION_FILE,
    RULES_FILE,
    TAXONOMY_FILE,
    WORKBOOK_FILE,
    read_config_version,
    write_config_version,
)
from cs_tickets.rule_coverage import computed_rule_targets, has_rule_target, rule_target_tiers
from cs_tickets.rule_generator import GeneratedRule, generate_rule_from_exemplar, rule_spec_to_dict
from cs_tickets.taxonomy import (
    TIER1_NOVELTY,
    AllowList,
    load_allowlist,
    merge_tuples_into_workbook,
    novelty_type_for_tuple,
    resolve_exemplars_for_tuples,
    split_taxonomy_proposals,
)

_LIVE_BACKUP_FILES = (TAXONOMY_FILE, RULES_FILE, CONFIG_VERSION_FILE, WORKBOOK_FILE)
_LIVE_ARTIFACT_FILES = (TAXONOMY_FILE, RULES_FILE, WORKBOOK_FILE)


class PromoteError(Exception):
    """Validation or merge failure during Confirm."""


@dataclass(frozen=True)
class ConfirmResult:
    proposal_id: str
    upload_id: str
    config_version_before: int
    config_version_after: int
    rules_added: int
    taxonomy_added: int
    workbook_rows_added: int
    rules_fallback_added: int
    live_dir: Path
    proposals_dir: Path
    accepted_rule_ids: tuple[str, ...]
    accepted_taxonomy_ids: tuple[str, ...]


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def allow_tier1_promote() -> bool:
    return (os.environ.get("ALLOW_TIER1_PROMOTE") or "").strip().lower() in ("1", "true", "yes", "on")


def rule_proposal_to_json(proposal: RuleProposal) -> dict[str, object]:
    rule_id = proposal.proposal_id
    if rule_id.startswith("rule."):
        rule_id = rule_id[5:]
    payload: dict[str, object] = {
        "id": rule_id,
        "tier": list(proposal.tier),
        "weight": proposal.weight,
    }
    if proposal.all_tags:
        payload["all_tags"] = list(proposal.all_tags)
    if proposal.any_tags:
        payload["any_tags"] = list(proposal.any_tags)
    if proposal.any_subject:
        payload["any_subject"] = list(proposal.any_subject)
    if proposal.any_blob:
        payload["any_blob"] = list(proposal.any_blob)
    return payload


def rule_proposal_to_spec(proposal: RuleProposal) -> RuleSpec:
    rule_id = proposal.proposal_id
    if rule_id.startswith("rule."):
        rule_id = rule_id[5:]
    return RuleSpec(
        id=rule_id,
        tier=proposal.tier,
        weight=proposal.weight,
        any_tags=proposal.any_tags,
        all_tags=proposal.all_tags,
        any_subject=proposal.any_subject,
        any_blob=proposal.any_blob,
    )


@dataclass(frozen=True)
class CandidateLiveConfig:
    allow_old: AllowList
    allow_new: AllowList
    rule_specs_new: tuple[RuleSpec, ...]
    selected_tuples: frozenset[tuple[str, str, str, str, str]]
    candidate_dir: Path


def release_candidate_live_config(config: CandidateLiveConfig) -> None:
    shutil.rmtree(config.candidate_dir, ignore_errors=True)


def _copy_live_artifacts(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for name in _LIVE_ARTIFACT_FILES:
        artifact = src / name
        if artifact.is_file():
            shutil.copy2(artifact, dst / name)


def _prepare_accepted_selection(
    live_dir: Path,
    *,
    rule_proposals: tuple[RuleProposal, ...],
    taxonomy_proposals: tuple[TaxonomyProposal, ...],
    accepted_rule_ids: frozenset[str],
    accepted_taxonomy_ids: frozenset[str],
) -> tuple[tuple[RuleProposal, ...], tuple[TaxonomyProposal, ...], frozenset[tuple[str, str, str, str, str]], AllowList]:
    validate_confirm_selection(
        rule_proposals,
        taxonomy_proposals,
        accepted_rule_ids=accepted_rule_ids,
        accepted_taxonomy_ids=accepted_taxonomy_ids,
    )
    accepted_rules = tuple(p for p in rule_proposals if p.proposal_id in accepted_rule_ids)
    tax_path = live_dir / TAXONOMY_FILE
    wb_path = live_dir / WORKBOOK_FILE
    allow_before = load_allowlist(
        tax_path if tax_path.is_file() else None,
        wb_path if wb_path.is_file() else None,
    )
    accepted_tax = _refresh_taxonomy_novelty(
        tuple(p for p in taxonomy_proposals if p.proposal_id in accepted_taxonomy_ids),
        allow_before,
    )
    if not allow_tier1_promote():
        blocked = [p.proposal_id for p in accepted_tax if p.novelty_type == TIER1_NOVELTY]
        if blocked:
            raise PromoteError(
                "New Tier1 segments require maintainer approval (set ALLOW_TIER1_PROMOTE=true)."
            )
    accepted_tuples = frozenset(p.tier for p in accepted_tax)
    _validate_rule_targets(accepted_rules, allow_before, accepted_tuples)
    return accepted_rules, accepted_tax, accepted_tuples, allow_before


def _apply_hybrid_merges_to_dir(
    target_dir: Path,
    *,
    upload_xlsx: Path | None,
    accepted_rules: tuple[RuleProposal, ...],
    accepted_tax: tuple[TaxonomyProposal, ...],
) -> tuple[int, int, int, int]:
    csv_proposals, workbook_tuples = split_taxonomy_proposals(accepted_tax)
    taxonomy_path = target_dir / TAXONOMY_FILE
    rules_path = target_dir / RULES_FILE
    workbook_path = target_dir / WORKBOOK_FILE

    taxonomy_text = taxonomy_path.read_text(encoding="utf-8")
    rules_text = rules_path.read_text(encoding="utf-8")
    taxonomy_text, taxonomy_added = merge_taxonomy_csv(taxonomy_text, csv_proposals)
    rules_text, rules_added = merge_rules_json(rules_text, accepted_rules)
    taxonomy_path.write_text(taxonomy_text, encoding="utf-8")
    rules_path.write_text(rules_text, encoding="utf-8")

    workbook_rows_added = 0
    if workbook_tuples:
        if upload_xlsx is None:
            raise PromoteError("Upload workbook required for granular category updates.")
        if not workbook_path.is_file():
            raise PromoteError(f"Live workbook missing: {WORKBOOK_FILE}")
        workbook_rows_added = merge_tuples_into_workbook(
            workbook_path,
            upload_xlsx,
            workbook_tuples,
        )

    accepted_tuples = frozenset(p.tier for p in accepted_tax)
    rules_fallback_added = _apply_rule_fallback(rules_path, upload_xlsx, accepted_tuples)
    _validate_accepted_tuples(target_dir, accepted_tuples)
    return taxonomy_added, rules_added, workbook_rows_added, rules_fallback_added


def build_candidate_live_config(
    live_dir: Path,
    *,
    upload_xlsx: Path | None,
    rule_proposals: tuple[RuleProposal, ...],
    taxonomy_proposals: tuple[TaxonomyProposal, ...],
    accepted_rule_ids: frozenset[str],
    accepted_taxonomy_ids: frozenset[str],
) -> CandidateLiveConfig:
    """Simulate Confirm in a temp copy of runs/live/ for NDJSON impact preview."""
    accepted_rules, accepted_tax, accepted_tuples, allow_before = _prepare_accepted_selection(
        live_dir,
        rule_proposals=rule_proposals,
        taxonomy_proposals=taxonomy_proposals,
        accepted_rule_ids=accepted_rule_ids,
        accepted_taxonomy_ids=accepted_taxonomy_ids,
    )
    candidate_dir = Path(tempfile.mkdtemp(prefix="cs_learn_candidate_"))
    _copy_live_artifacts(live_dir, candidate_dir)
    _apply_hybrid_merges_to_dir(
        candidate_dir,
        upload_xlsx=upload_xlsx,
        accepted_rules=accepted_rules,
        accepted_tax=accepted_tax,
    )
    tax = candidate_dir / TAXONOMY_FILE
    wb = candidate_dir / WORKBOOK_FILE
    allow_new = load_allowlist(
        tax if tax.is_file() else None,
        wb if wb.is_file() else None,
    )
    rule_specs_new = _load_rules_file(candidate_dir / RULES_FILE)
    return CandidateLiveConfig(
        allow_old=allow_before,
        allow_new=allow_new,
        rule_specs_new=rule_specs_new,
        selected_tuples=accepted_tuples,
        candidate_dir=candidate_dir,
    )


def _parse_taxonomy_csv_text(
    csv_text: str,
) -> tuple[list[str], dict[tuple[str, str, str, str], list[str]], list[str] | None]:
    reader = csv.reader(StringIO(csv_text))
    header = list(next(reader, None) or ["Tier1_Segment", "Tier2_Stream", "Tier3_Cat", "Tier4_Type"])
    paths: dict[tuple[str, str, str, str], list[str]] = {}
    order: list[tuple[str, str, str, str]] = []
    grand_total: list[str] | None = None
    carry = ["", "", "", ""]
    for row in reader:
        if not row or all(not (c or "").strip() for c in row):
            continue
        raw = [row[i].strip() if i < len(row) else "" for i in range(4)]
        joined = "".join(raw).strip().lower()
        if joined.startswith("grand total"):
            grand_total = list(row)
            break
        for i in range(4):
            if raw[i]:
                carry[i] = raw[i]
                for j in range(i + 1, 4):
                    carry[j] = ""
        path = _path_from_pivot_carry(carry)
        if path is None:
            continue
        if path not in paths:
            order.append(path)
        paths[path] = list(row)
    return header, {p: paths[p] for p in order}, grand_total


def _path_from_pivot_carry(carry: list[str]) -> tuple[str, str, str, str] | None:
    t1, t2, t3, t4 = (c.strip() for c in carry)
    if not t1:
        return None
    if t2 == "Junk" and not t3 and not t4:
        return (t1, "Junk", "Junk", "Junk")
    if t2 and t3 and t4:
        return (t1, t2, t3, t4)
    return None


def _pivot_row_for_path(
    path: tuple[str, str, str, str],
    prev: tuple[str, str, str, str] | None,
    *,
    header_len: int,
    tail: list[str],
) -> list[str]:
    t1, t2, t3, t4 = path
    if prev is None:
        cells = [t1, t2, t3, t4]
    else:
        p1, p2, p3, _p4 = prev
        if t1 != p1:
            cells = [t1, t2, t3, t4]
        elif t2 != p2:
            cells = ["", t2, t3, t4]
        elif t3 != p3:
            cells = ["", "", t3, t4]
        else:
            cells = ["", "", "", t4]
    row = cells + tail
    if len(row) < header_len:
        row.extend([""] * (header_len - len(row)))
    return row[:header_len]


def _serialize_taxonomy_csv(
    header: list[str],
    paths: dict[tuple[str, str, str, str], list[str]],
    ordered_paths: list[tuple[str, str, str, str]],
    grand_total: list[str] | None,
) -> str:
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    prev: tuple[str, str, str, str] | None = None
    for path in ordered_paths:
        source = paths[path]
        tail = source[4:] if len(source) > 4 else [""] * max(0, len(header) - 4)
        writer.writerow(_pivot_row_for_path(path, prev, header_len=len(header), tail=tail))
        prev = path
    if grand_total is not None:
        gt = list(grand_total)
        if len(gt) < len(header):
            gt.extend([""] * (len(header) - len(gt)))
        writer.writerow(gt[: len(header)])
    return buf.getvalue()


def merge_taxonomy_csv(csv_text: str, proposals: tuple[TaxonomyProposal, ...]) -> tuple[str, int]:
    header, path_rows, grand_total = _parse_taxonomy_csv_text(csv_text)
    existing = set(path_rows)
    added = 0
    for proposal in sorted(proposals, key=lambda p: p.tier[:4]):
        t1, t2, t3, t4, _granular = proposal.tier
        path = (t1, t2, t3, t4)
        if not t4 or path in existing:
            continue
        existing.add(path)
        path_rows[path] = [t1, t2, t3, t4] + ([""] * max(0, len(header) - 4))
        added += 1
    if not added:
        return csv_text if csv_text.endswith("\n") else csv_text + "\n", 0
    ordered = sorted(path_rows.keys())
    return _serialize_taxonomy_csv(header, path_rows, ordered, grand_total), added


def merge_rules_json(rules_text: str, proposals: tuple[RuleProposal, ...]) -> tuple[str, int]:
    data = json.loads(rules_text)
    if not isinstance(data, list):
        raise PromoteError("classifier_rules.json must contain a list")
    existing_ids = {str(item.get("id")) for item in data if isinstance(item, dict) and item.get("id")}
    added = 0
    for proposal in proposals:
        raw = rule_proposal_to_json(proposal)
        rule_id = str(raw["id"])
        if rule_id in existing_ids:
            continue
        data.append(raw)
        existing_ids.add(rule_id)
        added += 1
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", added


def validate_confirm_selection(
    rule_proposals: tuple[RuleProposal, ...],
    taxonomy_proposals: tuple[TaxonomyProposal, ...],
    *,
    accepted_rule_ids: frozenset[str],
    accepted_taxonomy_ids: frozenset[str],
) -> None:
    if not accepted_rule_ids and not accepted_taxonomy_ids:
        raise PromoteError("Select at least one rule or category path to confirm.")

    known_rules = {p.proposal_id for p in rule_proposals}
    unknown_rules = accepted_rule_ids - known_rules
    if unknown_rules:
        raise PromoteError(f"Unknown rule selection: {', '.join(sorted(unknown_rules)[:3])}")

    known_tax = {p.proposal_id for p in taxonomy_proposals}
    unknown_tax = accepted_taxonomy_ids - known_tax
    if unknown_tax:
        raise PromoteError(f"Unknown taxonomy selection: {', '.join(sorted(unknown_tax)[:3])}")

    if not allow_tier1_promote():
        blocked = [
            p.proposal_id
            for p in taxonomy_proposals
            if p.proposal_id in accepted_taxonomy_ids and p.novelty_type == TIER1_NOVELTY
        ]
        if blocked:
            raise PromoteError(
                "New Tier1 segments require maintainer approval (set ALLOW_TIER1_PROMOTE=true)."
            )


def backup_live_dir(live_dir: Path, backup_dir: Path) -> None:
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in _LIVE_BACKUP_FILES:
        src = live_dir / name
        if src.is_file():
            shutil.copy2(src, backup_dir / name)


def restore_live_dir(live_dir: Path, backup_dir: Path) -> None:
    for name in _LIVE_BACKUP_FILES:
        src = backup_dir / name
        dst = live_dir / name
        if src.is_file():
            shutil.copy2(src, dst)
        elif dst.is_file():
            dst.unlink()


def _append_generated_rules(rules_path: Path, generated: list[GeneratedRule]) -> int:
    if not generated:
        return 0
    existing: list[dict[str, object]] = []
    if rules_path.is_file():
        data = json.loads(rules_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise PromoteError("classifier_rules.json must contain a list")
        existing = data
    by_key = {str(item.get("tuple_key", "")): i for i, item in enumerate(existing) if item.get("tuple_key")}
    added = 0
    for item in generated:
        entry = rule_spec_to_dict(item.spec)
        key = item.spec.tuple_key
        if key in by_key:
            existing[by_key[key]] = entry
        else:
            by_key[key] = len(existing)
            existing.append(entry)
        added += 1
    rules_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return added


def _apply_rule_fallback(
    rules_path: Path,
    upload_xlsx: Path | None,
    tuples: frozenset[tuple[str, str, str, str, str]],
) -> int:
    if not tuples or upload_xlsx is None:
        return 0
    rules: tuple[RuleSpec, ...] = ()
    if rules_path.is_file():
        rules = _load_rules_file(rules_path)
    computed = computed_rule_targets()
    targets = rule_target_tiers(rules)
    exemplars = resolve_exemplars_for_tuples(upload_xlsx, tuples)
    generated: list[GeneratedRule] = []
    for tup in sorted(tuples):
        if has_rule_target(tup, json_rules=rules, computed_targets=computed):
            continue
        exemplar = exemplars.get(tup)
        if not exemplar:
            continue
        item = generate_rule_from_exemplar(
            exemplar,
            tup,
            existing_targets=targets,
            existing_rules=rules,
        )
        if item is None:
            continue
        generated.append(item)
        rules = rules + (item.spec,)
        targets = rule_target_tiers(rules)
    return _append_generated_rules(rules_path, generated)


def _refresh_taxonomy_novelty(
    proposals: tuple[TaxonomyProposal, ...],
    allow: AllowList,
) -> tuple[TaxonomyProposal, ...]:
    """Recompute novelty against current live allow-list at Confirm time."""
    return tuple(
        TaxonomyProposal(
            proposal_id=p.proposal_id,
            tier=p.tier,
            count=p.count,
            novelty_type=novelty_type_for_tuple(p.tier, allow),
            evidence_ids=p.evidence_ids,
        )
        for p in proposals
    )


def _validate_rule_targets(
    accepted_rules: tuple[RuleProposal, ...],
    allow_before: AllowList,
    accepted_tuples: frozenset[tuple[str, str, str, str, str]],
) -> None:
    allowed = allow_before.tuples | accepted_tuples
    blocked = [p.proposal_id for p in accepted_rules if p.tier not in allowed]
    if blocked:
        raise PromoteError(
            "Cannot confirm rules whose target tuple is not in the allow-list: "
            + ", ".join(sorted(blocked)[:3])
        )


def list_live_backup_versions(live_dir: Path) -> tuple[int, ...]:
    backup_root = live_dir / "backup"
    if not backup_root.is_dir():
        return ()
    versions: list[int] = []
    for entry in backup_root.iterdir():
        if entry.is_dir() and entry.name.isdigit():
            versions.append(int(entry.name))
    return tuple(sorted(versions))


def has_revertable_live_backup(live_dir: Path) -> bool:
    current = read_config_version(live_dir)
    if current <= 1:
        return False
    return (live_dir / "backup" / str(current - 1)).is_dir() or bool(list_live_backup_versions(live_dir))


def revert_latest_live_backup(live_dir: Path) -> int:
    """Restore runs/live/ from the most recent backup and decrement config version."""
    current = read_config_version(live_dir)
    if current <= 1:
        raise PromoteError("Nothing to revert.")
    backup_version = current - 1
    backup_dir = live_dir / "backup" / str(backup_version)
    if not backup_dir.is_dir():
        versions = list_live_backup_versions(live_dir)
        if not versions:
            raise PromoteError("No backup available to revert.")
        backup_version = versions[-1]
        backup_dir = live_dir / "backup" / str(backup_version)
    restore_live_dir(live_dir, backup_dir)
    write_config_version(
        live_dir,
        version=backup_version,
        proposal_id="revert",
        upload_id="revert",
    )
    return backup_version


def _validate_accepted_tuples(
    live_dir: Path,
    accepted_tuples: frozenset[tuple[str, str, str, str, str]],
) -> None:
    if not accepted_tuples:
        return
    tax = live_dir / TAXONOMY_FILE
    wb = live_dir / WORKBOOK_FILE
    allow = load_allowlist(
        tax if tax.is_file() else None,
        wb if wb.is_file() else None,
    )
    missing = accepted_tuples - allow.tuples
    if missing:
        sample = ", ".join(" / ".join(t) for t in sorted(missing)[:3])
        raise PromoteError(f"Confirm validation failed: tuple(s) not in allow-list after merge: {sample}")


def confirm_hybrid_proposals(
    live_dir: Path,
    *,
    upload_id: str,
    upload_filename: str,
    upload_xlsx: Path | None,
    rule_proposals: tuple[RuleProposal, ...],
    taxonomy_proposals: tuple[TaxonomyProposal, ...],
    accepted_rule_ids: frozenset[str],
    accepted_taxonomy_ids: frozenset[str],
) -> ConfirmResult:
    accepted_rules, accepted_tax, accepted_tuples, _allow_before = _prepare_accepted_selection(
        live_dir,
        rule_proposals=rule_proposals,
        taxonomy_proposals=taxonomy_proposals,
        accepted_rule_ids=accepted_rule_ids,
        accepted_taxonomy_ids=accepted_taxonomy_ids,
    )

    version_before = read_config_version(live_dir)
    proposal_id = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S") + f"-{upload_id[:8]}"
    backup_dir = live_dir / "backup" / str(version_before)
    backup_live_dir(live_dir, backup_dir)

    try:
        taxonomy_added, rules_added, workbook_rows_added, rules_fallback_added = (
            _apply_hybrid_merges_to_dir(
                live_dir,
                upload_xlsx=upload_xlsx,
                accepted_rules=accepted_rules,
                accepted_tax=accepted_tax,
            )
        )

        proposals_dir = live_dir.parent / "proposals" / proposal_id
        proposals_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "proposal_id": proposal_id,
            "upload_id": upload_id,
            "upload_filename": upload_filename,
            "confirmed_at": _utc_now_iso(),
            "config_version_before": version_before,
            "config_version_after": version_before + 1,
            "accepted_rule_ids": sorted(accepted_rule_ids),
            "accepted_taxonomy_ids": sorted(accepted_taxonomy_ids),
            "rules_added": rules_added,
            "taxonomy_added": taxonomy_added,
            "workbook_rows_added": workbook_rows_added,
            "rules_fallback_added": rules_fallback_added,
        }
        (proposals_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        if accepted_rules:
            (proposals_dir / "rules.json").write_text(
                json.dumps([rule_proposal_to_json(p) for p in accepted_rules], indent=2) + "\n",
                encoding="utf-8",
            )

        version_after = version_before + 1
        write_config_version(
            live_dir,
            version=version_after,
            proposal_id=proposal_id,
            upload_id=upload_id,
        )
    except Exception:
        restore_live_dir(live_dir, backup_dir)
        raise

    return ConfirmResult(
        proposal_id=proposal_id,
        upload_id=upload_id,
        config_version_before=version_before,
        config_version_after=version_after,
        rules_added=rules_added,
        taxonomy_added=taxonomy_added,
        workbook_rows_added=workbook_rows_added,
        rules_fallback_added=rules_fallback_added,
        live_dir=live_dir,
        proposals_dir=proposals_dir,
        accepted_rule_ids=tuple(sorted(accepted_rule_ids)),
        accepted_taxonomy_ids=tuple(sorted(accepted_taxonomy_ids)),
    )


def confirm_learn_proposals(  # backward-compatible alias (prod tests / older UI code)
    live_dir: Path,
    *,
    upload_id: str,
    upload_filename: str,
    rule_proposals: tuple[RuleProposal, ...],
    taxonomy_proposals: tuple[TaxonomyProposal, ...],
    accepted_rule_ids: frozenset[str],
    accepted_taxonomy_ids: frozenset[str],
) -> ConfirmResult:
    """
    Backwards-compatible wrapper for older naming.

    This variant does not provide `upload_xlsx`, so it is only safe when the
    confirmed selection does not include any `granular_new` / workbook merges.
    """
    return confirm_hybrid_proposals(
        live_dir,
        upload_id=upload_id,
        upload_filename=upload_filename,
        upload_xlsx=None,
        rule_proposals=rule_proposals,
        taxonomy_proposals=taxonomy_proposals,
        accepted_rule_ids=accepted_rule_ids,
        accepted_taxonomy_ids=accepted_taxonomy_ids,
    )
