"""Portal tests for TBC queue and re-classify (Phase A)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cs_tickets import portal_app
from cs_tickets.portal_app import app
from cs_tickets.portal_copy import TBC_QUEUE_BUTTON
from cs_tickets.portal_stats import is_manual_review_row


def _upload_sample_run(client: TestClient, repo_root: Path) -> str:
    export = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not export.is_file():
        pytest.skip("fixture missing")
    portal_app._RUNS.clear()
    resp = client.post(
        "/run",
        files={"export": ("sample.ndjson", export.read_bytes(), "application/octet-stream")},
    )
    assert resp.status_code == 200
    return next(iter(portal_app._RUNS))


def test_run_results_shows_tbc_queue_link_when_tbc(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    record = portal_app._RUNS[run_id]
    tbc_count = sum(1 for r in record.rows if is_manual_review_row(r))
    resp = client.get(f"/run/{run_id}/results")
    assert resp.status_code == 200
    if tbc_count:
        assert TBC_QUEUE_BUTTON in resp.text
        assert f'/run/{run_id}/tbc"' in resp.text


def test_tbc_queue_page_and_json(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    page = client.get(f"/run/{run_id}/tbc")
    assert page.status_code == 200
    assert "tbc-queue-app" in page.text
    assert "tbc_queue.js?v=" in page.text
    assert "Review focus" not in page.text
    assert "Quick focus" not in page.text
    assert "tbc-filter-nl" not in page.text
    assert "tbc-filter-chips" not in page.text
    assert "Contains" in page.text
    assert "Category focus" in page.text
    assert "Draft rule for filter" in page.text
    assert "Skip chunk" in page.text
    assert "Finish → run results" in page.text

    data = client.get(f"/run/{run_id}/tbc_queue?offset=0&limit=10").json()
    assert "rows" in data
    assert data["run_id"] == run_id
    assert data["limit"] == 10
    if data["rows"]:
        row = data["rows"][0]
        assert "ticket_id" in row
        assert "quote" in row
        assert "why_tbc" in row
        assert "suggested_tier" in row
        assert f"run_id={run_id}" in row["propose_rule_url"]


def test_tbc_parse_focus_endpoint(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    resp = client.post(
        f"/run/{run_id}/tbc_parse_focus",
        json={"text": "review B2C cancellation"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "filter" in data
    assert data.get("ok") is True or data.get("errors")


def test_tbc_draft_rule_for_filter_requires_focus(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    resp = client.post(f"/run/{run_id}/tbc_draft_rule_for_filter", json={})
    assert resp.status_code == 400


def test_tbc_queue_filter_query(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    data = client.get(f"/run/{run_id}/tbc_queue?q=zzznomatch&include_facets=1").json()
    assert "filter" in data
    assert data["filter"]["q"] == "zzznomatch"
    assert data["total_pending"] <= data["total_pending_unfiltered"]
    assert "facets" in data


def test_tbc_chunk_ack_reduces_pending(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    before = client.get(f"/run/{run_id}/tbc_queue").json()
    if not before["rows"]:
        pytest.skip("no TBC rows in fixture")
    ids = [r["ticket_id"] for r in before["rows"]]
    ack = client.post(
        f"/run/{run_id}/tbc_chunk/ack",
        json={"ticket_ids": ids},
    )
    assert ack.status_code == 200
    assert ack.json()["ok"] is True
    assert "queue_complete" in ack.json()
    after = client.get(f"/run/{run_id}/tbc_queue").json()
    assert after["total_pending"] == before["total_pending"] - len(ids)


def test_reclassify_run_updates_rows(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    resp = client.post(f"/run/{run_id}/reclassify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "tbc_before" in data
    assert "tbc_after" in data


def test_rules_confirm_forbidden_without_env(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PORTAL_ALLOW_CONFIRM", raising=False)
    client = TestClient(app)
    resp = client.post(
        "/rules/confirm",
        json={
            "rule": {
                "id": "test.forbidden",
                "tier": [
                    "B2C",
                    "Service Task",
                    "General Support",
                    "TBC (Manual Review)",
                    "N/A",
                ],
                "weight": 8,
                "any_blob": ["test phrase"],
            }
        },
    )
    assert resp.status_code == 403


def test_rules_new_prefill_from_run_ticket(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    record = portal_app._RUNS[run_id]
    tbc_row = next((r for r in record.rows if is_manual_review_row(r)), None)
    if tbc_row is None:
        pytest.skip("no TBC row")
    ticket_id = str(tbc_row["id"])
    resp = client.get(f"/rules/new?run_id={run_id}&ticket_id={ticket_id}")
    assert resp.status_code == 200
    assert 'id="rules-ticket-id"' in resp.text
    assert f'value="{ticket_id}"' in resp.text
    assert "Update: Map" in resp.text
    assert "TBC (Manual Review)" not in resp.text


def test_suggest_category_endpoint(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    record = portal_app._RUNS[run_id]
    tbc_row = next((r for r in record.rows if is_manual_review_row(r)), None)
    if tbc_row is None:
        import pytest

        pytest.skip("no TBC row")
    ticket_id = str(tbc_row["id"])
    resp = client.post(f"/run/{run_id}/suggest_category/{ticket_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "tier_path" in data
    assert "prefill" in data
    assert "source" in data
