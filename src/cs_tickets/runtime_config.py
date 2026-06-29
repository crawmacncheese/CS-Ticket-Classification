from __future__ import annotations

import json
import shutil
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from cs_tickets.classifier_rules import RuleSpec, _load_rules_file, load_rule_specs
from cs_tickets.drive_live_config import (
    drive_live_config_enabled,
    sync_live_from_drive_if_newer,
)
from cs_tickets.live_config import (
    CONFIG_VERSION_FILE,
    RULES_FILE,
    TAXONOMY_FILE,
    WORKBOOK_FILE,
    read_config_version,
    write_config_version,
)
from cs_tickets.repo_paths import training_rules_path
from cs_tickets.taxonomy import AllowList, load_allowlist

LIVE_SUBDIR = ("runs", "live")


def live_dir(repo_root: Path) -> Path:
    return repo_root.joinpath(*LIVE_SUBDIR)


def _seed_path(repo_root: Path, filename: str) -> Path | None:
    """Bootstrap source: references/ first, then doc/ (image fallback)."""
    for subdir in ("references", "doc"):
        candidate = repo_root / subdir / filename
        if candidate.is_file():
            return candidate
    return None


def _write_rules_json(path: Path, rules: tuple[RuleSpec, ...]) -> None:
    payload: list[dict[str, object]] = []
    for rule in rules:
        item: dict[str, object] = {
            "id": rule.id,
            "tier": list(rule.tier),
            "weight": rule.weight,
        }
        if rule.all_tags:
            item["all_tags"] = list(rule.all_tags)
        if rule.any_tags:
            item["any_tags"] = list(rule.any_tags)
        if rule.any_subject:
            item["any_subject"] = list(rule.any_subject)
        if rule.any_blob:
            item["any_blob"] = list(rule.any_blob)
        if rule.exclude_blob:
            item["exclude_blob"] = list(rule.exclude_blob)
        if rule.any_url:
            item["any_url"] = list(rule.any_url)
        if rule.requires_b2b_print_context:
            item["requires_b2b_print_context"] = True
        if rule.source:
            item["source"] = rule.source
        if rule.exemplar_id:
            item["exemplar_id"] = rule.exemplar_id
        if rule.tuple_key:
            item["tuple_key"] = rule.tuple_key
        payload.append(item)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _bootstrap_live_rules(repo_root: Path, target: Path) -> None:
    """Seed runs/live/classifier_rules.json from package core + doc/training_rules.json."""
    rules_dst = target / RULES_FILE
    if rules_dst.is_file():
        return
    core_path = Path(str(files("cs_tickets").joinpath(RULES_FILE)))
    merged = list(_load_rules_file(core_path))
    seen = {rule.id for rule in merged}
    training_path = training_rules_path()
    if training_path.is_file():
        for rule in _load_rules_file(training_path):
            if rule.id in seen:
                continue
            merged.append(rule)
            seen.add(rule.id)
    _write_rules_json(rules_dst, tuple(merged))


def ensure_live_bootstrapped(repo_root: Path) -> Path:
    """Create runs/live/ from references/doc seeds, then overlay Drive when enabled."""
    target = live_dir(repo_root)
    target.mkdir(parents=True, exist_ok=True)

    tax_dst = target / TAXONOMY_FILE
    if not tax_dst.is_file():
        tax_src = _seed_path(repo_root, TAXONOMY_FILE)
        if tax_src is not None:
            shutil.copy2(tax_src, tax_dst)
        else:
            tax_dst.write_text(
                "Tier1_Segment,Tier2_Stream,Tier3_Cat,Tier4_Type\n",
                encoding="utf-8",
            )

    _bootstrap_live_rules(repo_root, target)

    wb_dst = target / WORKBOOK_FILE
    if not wb_dst.is_file():
        wb_src = _seed_path(repo_root, WORKBOOK_FILE)
        if wb_src is not None:
            shutil.copy2(wb_src, wb_dst)

    if not (target / CONFIG_VERSION_FILE).is_file():
        write_config_version(target, version=1, proposal_id="bootstrap", upload_id="bootstrap")

    if drive_live_config_enabled():
        sync_live_from_drive_if_newer(target)

    return target


def refresh_live_from_drive(repo_root: Path) -> None:
    """Re-download live config from Drive (multi-replica freshness after Confirm)."""
    if not drive_live_config_enabled():
        return
    target = live_dir(repo_root)
    target.mkdir(parents=True, exist_ok=True)
    sync_live_from_drive_if_newer(target)
    invalidate_runtime_cache()


def runtime_config_enabled(repo_root: Path) -> bool:
    return ensure_live_bootstrapped(repo_root).is_dir()


@lru_cache(maxsize=8)
def _load_rule_specs_cached(rules_path: str, mtime_ns: int) -> tuple[RuleSpec, ...]:
    del mtime_ns
    return _load_rules_file(Path(rules_path))


def load_runtime_rule_specs(repo_root: Path) -> tuple[RuleSpec, ...]:
    live = ensure_live_bootstrapped(repo_root)
    rules_path = live / RULES_FILE
    if rules_path.is_file():
        stat = rules_path.stat()
        return _load_rule_specs_cached(str(rules_path.resolve()), stat.st_mtime_ns)
    return load_rule_specs()


def load_runtime_allowlist(repo_root: Path) -> AllowList:
    live = ensure_live_bootstrapped(repo_root)
    tax = live / TAXONOMY_FILE
    wb = live / WORKBOOK_FILE
    doc = repo_root / "doc"
    return load_allowlist(
        tax if tax.is_file() else None,
        wb if wb.is_file() else (doc / WORKBOOK_FILE if (doc / WORKBOOK_FILE).is_file() else None),
    )


def invalidate_runtime_cache() -> None:
    _load_rule_specs_cached.cache_clear()
    from cs_tickets.classifier_rules import load_rule_specs

    load_rule_specs.cache_clear()


def current_config_version(repo_root: Path) -> int:
    return read_config_version(ensure_live_bootstrapped(repo_root))
