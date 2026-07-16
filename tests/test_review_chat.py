"""Phase E — review chat orchestration endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cs_tickets import portal_app
from cs_tickets.portal_app import app


def _upload_christine_run(client: TestClient, repo_root: Path) -> str:
    export = repo_root / "tests" / "fixtures" / "christine_category_audit_fixture.ndjson"
    if not export.is_file():
        pytest.skip("christine fixture missing")
    portal_app._RUNS.clear()
    resp = client.post(
        "/run",
        files={"export": ("christine.ndjson", export.read_bytes(), "application/octet-stream")},
    )
    assert resp.status_code == 200
    return next(iter(portal_app._RUNS))


def test_review_chat_redirect(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.get(f"/run/{run_id}/review_chat", follow_redirects=False)
    assert resp.status_code == 302
    loc = resp.headers.get("location") or ""
    assert "/rules/new?" in loc
    assert f"run_id={run_id}" in loc
    assert "mode=orch" in loc


def test_rules_new_orch_mode_badge(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.get(f"/rules/new?run_id={run_id}&mode=orch")
    assert resp.status_code == 200
    assert 'data-orchestration="true"' in resp.text
    assert "rules-orch-badge" in resp.text
    assert "rules.js?v=22" in resp.text


def test_review_chat_turn_junk_clarifies(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.post(
        f"/run/{run_id}/review_chat/turn",
        json={"text": "gsdfsaf"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is False
    assert data.get("workbench_filter") is None
    types = [c.get("type") for c in data.get("cards") or []]
    assert "clarify" in types


def test_review_chat_turn_show_not_contested(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.post(
        f"/run/{run_id}/review_chat/turn",
        json={"text": "show not contested"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    wf = data.get("workbench_filter") or {}
    assert wf.get("tbc_reason") == "!lost_margin"
    assert wf.get("active") is True


def test_review_chat_turn_show_contested(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.post(
        f"/run/{run_id}/review_chat/turn",
        json={"text": "show contested"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    wf = data.get("workbench_filter") or {}
    assert wf.get("tbc_reason") == "lost_margin"
    assert wf.get("active") is True
    assert data.get("profile", {}).get("parse_ok") is True
    summary = data.get("parse_summary") or ""
    assert "Understood as:" in summary
    assert "Contested" in summary or "contested" in summary.lower()


def test_review_chat_turn_only_contested_parse_summary(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.post(
        f"/run/{run_id}/review_chat/turn",
        json={"text": "only contested"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert (data.get("workbench_filter") or {}).get("tbc_reason") == "lost_margin"
    summary = data.get("parse_summary") or ""
    assert "Understood as:" in summary
    assert "Contested" in summary
    assert "lost_margin" not in summary
    assert "[deterministic]" not in summary


def test_review_chat_turn_profile_cards(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.post(
        f"/run/{run_id}/review_chat/turn",
        json={"text": "review B2C"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("mode") == "audit"
    types = [c.get("type") for c in data.get("cards") or []]
    assert "profile_summary" in types
    wf = data.get("workbench_filter") or {}
    assert wf.get("tier1") == "B2C"
    assert wf.get("active") is True
    sweeps = [c for c in data["cards"] if c.get("type") == "sweep"]
    assert any(c.get("sweep_id") == "rosetta_system_email" for c in sweeps)
    assert any(c.get("match_count", 0) > 0 for c in sweeps)
    # Taxonomy compile phrase for Rosetta when available
    rosetta = next(c for c in sweeps if c.get("sweep_id") == "rosetta_system_email")
    assert rosetta.get("compile_phrase")


def test_review_chat_turn_zero_matches_clarify(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.post(
        f"/run/{run_id}/review_chat/turn",
        json={"text": 'review B2C "xyzzz_never_match_999"'},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("profile", {}).get("no_op") is True
    types = [c.get("type") for c in data.get("cards") or []]
    assert "clarify" in types
    assert data.get("suggested_compile") is None


def test_results_page_has_review_chat_dock(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.get(f"/run/{run_id}/results")
    assert resp.status_code == 200
    assert "Review chat" in resp.text
    assert 'id="workbench-layout"' in resp.text
    assert 'id="review-dock"' in resp.text
    assert 'data-dock="true"' in resp.text
    assert f"/run/{run_id}/review_chat" in resp.text  # pop-out
    assert "review_dock.js" in resp.text
    assert "rules.js?v=22" in resp.text


def test_category_audit_has_review_chat_dock(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.get(f"/run/{run_id}/category_audit")
    assert resp.status_code == 200
    assert "Review chat" in resp.text
    assert 'id="workbench-layout"' in resp.text
    assert 'id="review-dock"' in resp.text
    assert f"/run/{run_id}/review_chat" in resp.text


def test_tbc_queue_has_review_chat_dock(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.get(f"/run/{run_id}/tbc")
    assert resp.status_code == 200
    assert 'id="workbench-layout"' in resp.text
    assert 'id="review-dock"' in resp.text
    assert "tbc_queue.js" in resp.text
    assert "review_dock.js" in resp.text


def test_review_chat_log_without_session_md(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_christine_run(client, repo_root)
    resp = client.post(
        f"/run/{run_id}/review_chat/log",
        json={"action": "NOTE", "result": "ui only"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data.get("logged") is False
    assert data.get("log_entry", {}).get("action") == "NOTE"
