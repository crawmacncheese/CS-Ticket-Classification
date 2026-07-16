"""Portal tests for category audit (Phases 1–4)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cs_tickets import portal_app
from cs_tickets.category_audit_filters import CategoryAuditFilter
from cs_tickets.portal_category_audit import build_category_audit_context
from cs_tickets.portal_app import app


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


def test_run_results_shows_category_audit_button(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    resp = client.get(f"/run/{run_id}/results")
    assert resp.status_code == 200
    assert "Category audit" in resp.text
    assert f'/run/{run_id}/category_audit"' in resp.text


def test_tier_breakdown_has_audit_links(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    resp = client.get(f"/run/{run_id}/results")
    assert resp.status_code == 200
    assert "category-audit-tier-link" in resp.text
    assert f"/run/{run_id}/category_audit?" in resp.text


def test_category_audit_page_and_filters(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    page = client.get(f"/run/{run_id}/category_audit")
    assert page.status_code == 200
    assert "category-audit-app" in page.text
    assert "category_audit.js?v=7" in page.text
    assert "Slice checks" not in page.text
    assert "Full content" in page.text
    assert "Review focus (natural language)" not in page.text
    assert 'id="review-dock"' in page.text
    assert "category-audit-reclassify-btn" in page.text
    assert "category-audit-sweep-rule-compile" not in page.text

    filtered = client.get(f"/run/{run_id}/category_audit?tier1=B2C")
    assert filtered.status_code == 200


def test_category_audit_sweeps_json(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    resp = client.get(f"/run/{run_id}/category_audit/sweeps")
    assert resp.status_code == 200
    data = resp.json()
    assert "sweeps" in data
    assert len(data["sweeps"]) >= 1
    assert any(s.get("id") == "possible_duplicates" for s in data["sweeps"])
    assert all("match_count" in s for s in data["sweeps"])


def test_category_audit_pagination(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    resp = client.get(f"/run/{run_id}/category_audit?offset=0&limit=2")
    assert resp.status_code == 200
    assert "category-audit-card" in resp.text or "No tickets match" in resp.text


def test_category_audit_parse_focus_endpoint(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    resp = client.post(
        f"/run/{run_id}/category_audit_parse_focus",
        json={"text": "review B2C cancellation"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "audit_filter" in data
    assert "audit_url" in data
    assert data.get("ok") is True or data.get("errors")


def test_category_audit_unknown_run_404() -> None:
    client = TestClient(app)
    resp = client.get("/run/not-a-real-run/category_audit")
    assert resp.status_code == 404


def test_reclassify_snapshot_audit_and_banner(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    record = portal_app._RUNS[run_id]
    filt = CategoryAuditFilter.from_query(tier1="B2C")
    slice_before = len(build_category_audit_context(record.rows, filt)[0])

    resp = client.post(
        f"/run/{run_id}/reclassify",
        json={"snapshot_audit": True, "tier1": "B2C"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "audit_reclassify" in data
    ar = data["audit_reclassify"]
    assert ar["slice_count_before"] == slice_before
    assert ar["slice_count_after"] == slice_before
    assert ar["filter"]["tier1"] == "B2C"
    assert "tbc_before" in ar
    assert "tbc_after" in ar

    page = client.get(f"/run/{run_id}/category_audit?tier1=B2C&reclassified=1")
    assert page.status_code == 200
    assert "category-audit-reclassify-banner" in page.text
    assert "After re-classify" in page.text

    other = client.get(f"/run/{run_id}/category_audit?tier1=B2B&reclassified=1")
    assert "category-audit-reclassify-banner" not in other.text


def test_category_audit_export_csv(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    resp = client.get(f"/run/{run_id}/category_audit/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    body = resp.content.decode("utf-8-sig")
    assert "id,subject,requester_email,description" in body
    assert "attachment" in resp.headers.get("content-disposition", "").lower()


def test_category_audit_export_csv_respects_filter(repo_root: Path) -> None:
    client = TestClient(app)
    run_id = _upload_sample_run(client, repo_root)
    full = client.get(f"/run/{run_id}/category_audit/export.csv")
    filtered = client.get(f"/run/{run_id}/category_audit/export.csv?tier1=B2C")
    assert full.status_code == 200
    assert filtered.status_code == 200
    full_lines = full.content.decode("utf-8-sig").strip().splitlines()
    filt_lines = filtered.content.decode("utf-8-sig").strip().splitlines()
    assert len(filt_lines) <= len(full_lines)
