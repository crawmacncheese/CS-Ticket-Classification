from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cs_tickets import portal_app
from cs_tickets.portal_app import app
from cs_tickets.taxonomy import load_allowlist
from cs_tickets.tbc_trends import append_export_snapshot, init_db, trends_db_path

client = TestClient(app)


def test_dashboard_empty_when_no_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "missing.db"
    monkeypatch.setenv("TBC_TRENDS_DB_PATH", str(db))
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "TBC trends" in r.text
    assert "No trend database" in r.text
    assert 'href="/"' in r.text


def test_dashboard_with_snapshot_db(repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    ndjson = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not tax.is_file() or not ref.is_file() or not ndjson.is_file():
        pytest.skip("fixtures missing")

    db = tmp_path / "tbc.db"
    allow = load_allowlist(tax, ref)
    conn = init_db(db)
    append_export_snapshot(conn, ndjson, allow)
    conn.close()

    monkeypatch.setenv("TBC_TRENDS_DB_PATH", str(db))
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "5 tickets tracked" in r.text
    assert "Weekly TBC rate" in r.text
    assert "Top TBC tags" in r.text
    assert "Subject clusters" in r.text
    assert "stats-table" in r.text


def test_dashboard_shows_events(repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    ndjson = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not tax.is_file() or not ref.is_file() or not ndjson.is_file():
        pytest.skip("fixtures missing")

    db = tmp_path / "tbc.db"
    events = tmp_path / "events.json"
    events.write_text(
        '[{"date": "2026-05-14", "label": "Rule batch 3"}]',
        encoding="utf-8",
    )
    allow = load_allowlist(tax, ref)
    conn = init_db(db)
    append_export_snapshot(conn, ndjson, allow)
    conn.close()

    monkeypatch.setenv("TBC_TRENDS_DB_PATH", str(db))
    monkeypatch.setenv("TBC_TRENDS_EVENTS_PATH", str(events))
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "Rule batch 3" in r.text
    assert "2026-05-14" in r.text


def test_index_links_to_dashboard() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/dashboard"' in r.text
    assert "TBC trends dashboard" in r.text


def test_run_auto_snapshot_when_enabled(
    repo_root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    ndjson = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not tax.is_file() or not ref.is_file() or not ndjson.is_file():
        pytest.skip("fixtures missing")

    db = tmp_path / "auto.db"
    monkeypatch.setenv("TBC_TRENDS_ENABLED", "true")
    monkeypatch.setenv("TBC_TRENDS_DB_PATH", str(db))
    monkeypatch.setattr(portal_app, "resolve_repo_root", lambda: repo_root)

    portal_app._RUNS.clear()
    r = client.post(
        "/run",
        files={"export": ("five_tickets.ndjson", ndjson.read_bytes(), "application/octet-stream")},
    )
    assert r.status_code == 200
    assert "Added to" in r.text
    assert "/dashboard" in r.text
    assert db.is_file()
    conn = init_db(db)
    count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    conn.close()
    assert count == 5


def test_trends_db_path_default(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TBC_TRENDS_DB_PATH", raising=False)
    path = trends_db_path(repo_root)
    assert path == repo_root / "reports" / "tbc_trends" / "tbc_trends.db"
