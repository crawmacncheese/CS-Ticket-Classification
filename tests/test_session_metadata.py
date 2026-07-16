"""Tests for Session Metadata Package + runner gate (Phase B)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cs_tickets import portal_app
from cs_tickets.portal_app import app
from cs_tickets.session_metadata import (
    ROSETTA_COMPILE_PHRASE,
    SessionMetadataError,
    build_rosetta_package,
    package_from_profile,
    parse_package,
    resolve_sweep_id,
    validate_package_dict,
)
from cs_tickets.session_profile import SessionProfile, SweepSummary, build_session_profile
from cs_tickets.taxonomy import load_allowlist


def _load_allowlist(repo_root: Path):
    tax = repo_root / "doc" / "Taxonomy.csv"
    wb = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not wb.is_file():
        pytest.skip("allow-list fixtures missing")
    return load_allowlist(tax, wb)


def _upload_christine_run(client: TestClient, repo_root: Path) -> str:
    export = repo_root / "tests" / "fixtures" / "christine_category_audit_fixture.ndjson"
    if not export.is_file():
        pytest.skip("christine fixture missing")
    portal_app._RUNS.clear()
    resp = client.post(
        "/run",
        files={"export": (export.name, export.read_bytes(), "application/x-ndjson")},
    )
    assert resp.status_code == 200
    return next(iter(portal_app._RUNS))


def _noop_profile() -> SessionProfile:
    return SessionProfile(
        focus_nl="review B2C category: ZzzNone",
        audit_filter={
            "q": "",
            "tier1": "B2C",
            "categories": ["ZzzNone"],
            "tier4": "",
            "include_tbc": False,
            "active": True,
        },
        slice_count=0,
        tbc_count=0,
        sweep_summaries=(SweepSummary("rosetta_system_email", 0, ()),),
        no_op=True,
        parse_ok=True,
        parse_source="deterministic",
    )


def test_resolve_sweep_id_aliases() -> None:
    assert resolve_sweep_id("rosetta_footer") == "rosetta_system_email"
    assert resolve_sweep_id("rosetta_system_email") == "rosetta_system_email"


def test_validate_package_rejects_clarify_with_queue() -> None:
    raw = {
        "session_id": "sess_x",
        "run_id": None,
        "run_mode": "CATEGORY_AUDIT",
        "user_persona": "ANALYST",
        "taxonomy_version": 1,
        "profile": {"no_op": True},
        "orchestration_queue": [{"action": "PARSE_FOCUS", "params": {"text": "x"}}],
        "blockers": ["ZERO_MATCHES"],
        "clarify_message": "no matches",
    }
    errors = validate_package_dict(raw)
    assert any("empty orchestration_queue" in e for e in errors)


def test_parse_package_roundtrip() -> None:
    profile = SessionProfile(
        focus_nl="review B2C",
        audit_filter={"tier1": "B2C", "categories": [], "q": "", "tier4": "", "include_tbc": False, "active": True},
        slice_count=3,
        tbc_count=1,
        sweep_summaries=(SweepSummary("rosetta_system_email", 1, ("170002",)),),
        no_op=False,
        parse_ok=True,
        parse_source="deterministic",
    )
    pkg = build_rosetta_package(profile, run_id="abc", user_persona="ANALYST")
    assert pkg.is_actionable
    assert "NEEDS_LEAD_CONFIRM" in pkg.blockers
    assert any(a.action == "COMPILE_RULE_DRAFT" for a in pkg.orchestration_queue)
    assert any(a.action == "QUEUE_FOR_CONFIRMATION" for a in pkg.orchestration_queue)
    assert not any(a.action == "CONFIRM_RULE" for a in pkg.orchestration_queue)

    again = parse_package(pkg.as_dict())
    assert again.session_id == pkg.session_id
    assert again.orchestration_queue[0].action == "PARSE_FOCUS"


def test_zero_matches_package_not_actionable() -> None:
    pkg = package_from_profile(_noop_profile(), run_id="r1", rule_prefill=ROSETTA_COMPILE_PHRASE)
    assert not pkg.is_actionable
    assert pkg.has_terminal_blockers
    assert pkg.orchestration_queue == ()
    assert "ZERO_MATCHES" in pkg.blockers
    assert pkg.clarify_message


def test_runner_gate_skips_execution_on_zero_matches() -> None:
    pkg = package_from_profile(_noop_profile(), run_id="r1")
    ok, msg = pkg.runner_gate()
    assert ok is False
    assert not pkg.is_actionable
    assert "match" in msg.lower() or "scope" in msg.lower() or "blocker" in msg.lower()


def test_rosetta_package_from_christine_fixture(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    rows = portal_app._RUNS[run_id].rows
    allow = _load_allowlist(repo_root)
    profile = build_session_profile(rows, "review B2C", allow, use_llm=False)
    pkg = build_rosetta_package(profile, run_id=run_id, user_persona="ANALYST")

    assert pkg.is_actionable
    actions = [a.action for a in pkg.orchestration_queue]
    assert actions[0] == "PARSE_FOCUS"
    assert "EXECUTE_SWEEP" in actions
    assert "COMPILE_RULE_DRAFT" in actions
    assert "PREVIEW_RULE" in actions
    assert actions[-1] == "QUEUE_FOR_CONFIRMATION"

    sweep = next(a for a in pkg.orchestration_queue if a.action == "EXECUTE_SWEEP")
    assert sweep.params.get("sweep_id") == "rosetta_system_email"

    compile_step = next(a for a in pkg.orchestration_queue if a.action == "COMPILE_RULE_DRAFT")
    assert "Rosetta" in str(compile_step.params.get("rule_prefill") or "")


def test_parse_package_rejects_unknown_action() -> None:
    raw = {
        "session_id": "sess_x",
        "run_id": "r",
        "run_mode": "CATEGORY_AUDIT",
        "user_persona": "ANALYST",
        "taxonomy_version": 1,
        "profile": {},
        "orchestration_queue": [{"action": "CLARIFY"}],
        "blockers": [],
    }
    with pytest.raises(SessionMetadataError):
        parse_package(raw)


def test_write_sample_package_json_shape(tmp_path: Path) -> None:
    profile = SessionProfile(
        focus_nl="review B2C",
        audit_filter={"tier1": "B2C", "categories": [], "q": "", "tier4": "", "include_tbc": False, "active": True},
        slice_count=7,
        tbc_count=0,
        sweep_summaries=(SweepSummary("rosetta_system_email", 1, ("170002",)),),
        no_op=False,
        parse_ok=True,
        parse_source="deterministic",
    )
    pkg = build_rosetta_package(profile, run_id=None, user_persona="ANALYST")
    path = tmp_path / "rosetta_package.json"
    path.write_text(json.dumps(pkg.as_dict(), indent=2), encoding="utf-8")
    loaded = parse_package(json.loads(path.read_text(encoding="utf-8")))
    assert loaded.is_actionable
