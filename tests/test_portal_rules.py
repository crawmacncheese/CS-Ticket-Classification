"""Portal smoke tests for /rules routes."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from cs_tickets.portal_app import app


def test_rules_list_page_renders() -> None:
    client = TestClient(app)
    resp = client.get("/rules")
    assert resp.status_code == 200
    assert "Routing Rules" in resp.text
    assert "Add rule" in resp.text


def test_rules_new_page_renders() -> None:
    client = TestClient(app)
    resp = client.get("/rules/new")
    assert resp.status_code == 200
    assert "rules-app" in resp.text


def test_rules_compile_endpoint(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        import pytest

        pytest.skip("doc artifacts missing")
    client = TestClient(app)
    resp = client.post(
        "/rules/compile",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": 'Update: Map "Stripe payment completed" to System Report.',
                }
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("ok") is True
    assert data["rule"]["tier"][3] == "System Report"


def test_rules_parse_focus_endpoint(repo_root: Path) -> None:
    client = TestClient(app)
    resp = client.post("/rules/parse_focus", json={"text": "review B2C cancellation"})
    assert resp.status_code == 200
    data = resp.json()
    assert "rule_filter" in data
    assert "rules_url" in data
    assert data.get("ok") is True or data.get("errors")
