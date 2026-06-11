import csv
import json
from pathlib import Path

import pytest

from cs_tickets.pipeline import iter_master_rows, run_to_csv
from cs_tickets.taxonomy import load_allowlist


def test_pipeline_sample_export(repo_root: Path, tmp_path: Path) -> None:
    export = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not export.is_file() or not tax.is_file() or not xlsx.is_file():
        pytest.skip("fixtures missing")
    allow = load_allowlist(tax, xlsx)
    out = tmp_path / "out.csv"
    n, warns = run_to_csv(export, allow, out, limit=5)
    assert n == 5
    with out.open(newline="") as f:
        r = csv.DictReader(f)
        rows = list(r)
    assert len(rows) == 5
    assert set(rows[0].keys()) >= {"id", "tags", "Tier1_Segment", "Granular_Tech_UI_Type"}
    for row in rows:
        t = (
            row["Tier1_Segment"],
            row["Tier2_Stream"],
            row["Tier3_Cat"],
            row["Tier4_Type"],
            row["Granular_Tech_UI_Type"],
        )
        assert t in allow.tuples


def test_pipeline_pretty_printed_single_json_object(tmp_path: Path, repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("fixtures missing")
    allow = load_allowlist(tax, xlsx)
    ticket = {
        "url": "https://example.zendesk.com/api/v2/tickets/99.json",
        "id": 99,
        "external_id": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "generated_timestamp": 1,
        "type": "question",
        "subject": "Hello",
        "raw_subject": "Hello",
        "description": "",
        "priority": "normal",
        "status": "open",
        "follower_ids": [],
        "email_cc_ids": [],
        "forum_topic_id": None,
        "problem_id": None,
        "has_incidents": False,
        "is_public": True,
        "due_at": None,
        "tags": ["app"],
    }
    p = tmp_path / "one-ticket.json"
    p.write_text(json.dumps(ticket, indent=2), encoding="utf-8")
    out = tmp_path / "out.csv"
    n, _ = run_to_csv(p, allow, out, limit=10)
    assert n == 1


def test_pipeline_two_minified_objects_on_one_line(tmp_path: Path, repo_root: Path) -> None:
    """Some exports concatenate JSON objects without newlines; raw_decode must handle that."""
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("fixtures missing")
    allow = load_allowlist(tax, xlsx)
    a = {"url": "https://example.zendesk.com/api/v2/tickets/1.json", "id": 1, "tags": ["a"]}
    b = {"url": "https://example.zendesk.com/api/v2/tickets/2.json", "id": 2, "tags": ["b"]}
    p = tmp_path / "two.json"
    p.write_text(json.dumps(a, separators=(",", ":")) + json.dumps(b, separators=(",", ":")), encoding="utf-8")
    out = tmp_path / "out.csv"
    n, _ = run_to_csv(p, allow, out, limit=10)
    assert n == 2


def test_pipeline_bad_satisfaction_only_filter(tmp_path: Path, repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("fixtures missing")
    allow = load_allowlist(tax, xlsx)
    tickets = [
        {
            "url": "https://example.zendesk.com/api/v2/tickets/1.json",
            "id": 1,
            "tags": ["app"],
            "satisfaction_rating": {"score": "bad"},
        },
        {
            "url": "https://example.zendesk.com/api/v2/tickets/2.json",
            "id": 2,
            "tags": ["app"],
            "satisfaction_rating": {"score": "good"},
        },
        {
            "url": "https://example.zendesk.com/api/v2/tickets/3.json",
            "id": 3,
            "tags": ["app"],
        },
    ]
    p = tmp_path / "ratings.ndjson"
    p.write_text("\n".join(json.dumps(t) for t in tickets), encoding="utf-8")
    rows = list(iter_master_rows(p, allow, bad_satisfaction_only=True))
    assert len(rows) == 1
    assert rows[0][0]["id"] == 1
    out = tmp_path / "out.csv"
    n, _ = run_to_csv(p, allow, out, bad_satisfaction_only=True)
    assert n == 1
