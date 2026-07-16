"""Tests for Christine session profile (Phase A)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cs_tickets import portal_app
from cs_tickets.portal_app import app
from cs_tickets.session_profile import build_session_profile, compute_no_op
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


def test_compute_no_op_true_when_empty_slice_and_zero_sweeps() -> None:
    from cs_tickets.session_profile import SweepSummary

    assert compute_no_op(
        slice_count=0,
        sweep_summaries=(SweepSummary("rosetta_system_email", 0, ()),),
    )


def test_compute_no_op_false_when_sweep_matches() -> None:
    from cs_tickets.session_profile import SweepSummary

    assert not compute_no_op(
        slice_count=0,
        sweep_summaries=(SweepSummary("rosetta_system_email", 1, ("170002",)),),
    )


def test_session_profile_christine_fixture_reports_rosetta_sweep(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    rows = portal_app._RUNS[run_id].rows
    allow = _load_allowlist(repo_root)

    profile = build_session_profile(
        rows,
        "review B2C",
        allow,
        use_llm=False,
    )

    assert profile.parse_ok
    assert profile.parse_source == "deterministic"
    assert profile.audit_filter.get("tier1") == "B2C"
    assert profile.slice_count > 0
    assert profile.tbc_count >= 0
    assert not profile.no_op

    rosetta = next(
        (s for s in profile.sweep_summaries if s.sweep_id == "rosetta_system_email"),
        None,
    )
    assert rosetta is not None
    assert rosetta.match_count >= 1
    assert "170002" in rosetta.sample_ids


def test_session_profile_zero_matches_sets_no_op(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    rows = portal_app._RUNS[run_id].rows
    allow = _load_allowlist(repo_root)

    profile = build_session_profile(
        rows,
        "review B2C category: ZzzNonexistentCategoryOnly",
        allow,
        use_llm=False,
    )

    assert profile.slice_count == 0
    assert profile.no_op
    assert profile.blockers == ("ZERO_MATCHES",)
    assert profile.clarify_message
