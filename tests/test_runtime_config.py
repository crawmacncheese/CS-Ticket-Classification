from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cs_tickets.classifier_rules import load_rule_specs, set_active_rule_specs
from cs_tickets.live_config import CONFIG_VERSION_FILE, RULES_FILE, TAXONOMY_FILE, WORKBOOK_FILE
from cs_tickets.runtime_config import (
    current_config_version,
    ensure_live_bootstrapped,
    invalidate_runtime_cache,
    live_dir,
    load_runtime_allowlist,
    load_runtime_rule_specs,
)
from cs_tickets.taxonomy import load_allowlist


@pytest.fixture(autouse=True)
def _reset_runtime_state() -> None:
    yield
    set_active_rule_specs(None)
    load_rule_specs.cache_clear()
    invalidate_runtime_cache()


def _seed_doc_tree(repo_root: Path, target: Path) -> None:
    shutil.copytree(repo_root / "doc", target / "doc")


def test_live_dir_path() -> None:
    root = Path("/tmp/project")
    assert live_dir(root) == Path("/tmp/project/runs/live")


def test_bootstrap_creates_live_artifacts(tmp_path: Path, repo_root: Path) -> None:
    _seed_doc_tree(repo_root, tmp_path)
    live = ensure_live_bootstrapped(tmp_path)
    assert live.is_dir()
    assert (live / TAXONOMY_FILE).is_file()
    assert (live / RULES_FILE).is_file()
    assert (live / WORKBOOK_FILE).is_file()
    assert (live / CONFIG_VERSION_FILE).is_file()


def test_runtime_allowlist_matches_doc_union(tmp_path: Path, repo_root: Path) -> None:
    _seed_doc_tree(repo_root, tmp_path)
    doc_tax = tmp_path / "doc" / TAXONOMY_FILE
    doc_wb = tmp_path / "doc" / WORKBOOK_FILE
    expected = load_allowlist(doc_tax, doc_wb)
    ensure_live_bootstrapped(tmp_path)
    runtime = load_runtime_allowlist(tmp_path)
    assert runtime.tuples == expected.tuples


def test_runtime_rules_match_core_plus_training(tmp_path: Path, repo_root: Path) -> None:
    _seed_doc_tree(repo_root, tmp_path)
    set_active_rule_specs(None)
    load_rule_specs.cache_clear()
    expected = load_rule_specs()
    ensure_live_bootstrapped(tmp_path)
    runtime = load_runtime_rule_specs(tmp_path)
    assert runtime == expected


def test_bootstrap_rules_json_is_valid_list(tmp_path: Path, repo_root: Path) -> None:
    _seed_doc_tree(repo_root, tmp_path)
    live = ensure_live_bootstrapped(tmp_path)
    data = json.loads((live / RULES_FILE).read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data


def test_config_version_starts_at_one(tmp_path: Path, repo_root: Path) -> None:
    _seed_doc_tree(repo_root, tmp_path)
    ensure_live_bootstrapped(tmp_path)
    assert current_config_version(tmp_path) == 1


def test_bootstrap_is_idempotent(tmp_path: Path, repo_root: Path) -> None:
    _seed_doc_tree(repo_root, tmp_path)
    first = ensure_live_bootstrapped(tmp_path)
    first_tax = (first / TAXONOMY_FILE).read_bytes()
    second = ensure_live_bootstrapped(tmp_path)
    assert second == first
    assert (second / TAXONOMY_FILE).read_bytes() == first_tax


def test_invalidate_runtime_cache_after_rules_touch(
    tmp_path: Path, repo_root: Path,
) -> None:
    _seed_doc_tree(repo_root, tmp_path)
    ensure_live_bootstrapped(tmp_path)
    first = load_runtime_rule_specs(tmp_path)
    rules_path = tmp_path / "runs" / "live" / RULES_FILE
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    data.append(
        {
            "id": "test.runtime.cache",
            "tier": ["B2C", "Service Task", "General Support", "TBC (Manual Review)", "N/A"],
            "weight": 10.0,
            "any_tags": ["cache_probe"],
        }
    )
    rules_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    second = load_runtime_rule_specs(tmp_path)
    assert len(second) == len(first) + 1
    invalidate_runtime_cache()
    third = load_runtime_rule_specs(tmp_path)
    assert len(third) == len(second)


def test_drive_live_config_disabled_by_default() -> None:
    from cs_tickets.drive_live_config import drive_live_config_enabled

    assert drive_live_config_enabled() is False
