from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from openpyxl import Workbook

from cs_tickets.allowlist_compare import compare_allowlists_on_ndjson
from cs_tickets.allowlist_training import (
    commit_session,
    create_session,
    drop_session,
    revert_latest_snapshot,
    training_available,
)
from cs_tickets.schema import MASTER_COLUMNS, TIER_COLUMNS
from cs_tickets.taxonomy import load_allowlist

SHEET = "SCMP_Tickets_Master_Categorized"


def _write_workbook(path: Path, rows: list[dict[str, str]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(list(MASTER_COLUMNS))
    for row in rows:
        ws.append([row.get(c, "") for c in MASTER_COLUMNS])
    wb.save(path)


def _sample_row(**tier_overrides: str) -> dict[str, str]:
    row = {c: "" for c in MASTER_COLUMNS}
    row["id"] = tier_overrides.pop("id", "1")
    row["subject"] = tier_overrides.pop("subject", "Test")
    for col in TIER_COLUMNS:
        row[col] = tier_overrides.get(col, "Val")
    return row


def test_compare_allowlists_on_pretty_json_array(repo_root: Path, tmp_path: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, ref)
    export = tmp_path / "tickets.json"
    export.write_text(
        """[
  {"id": 1, "subject": "Help with login", "description": "Cannot sign in"},
  {"id": 2, "subject": "Billing question", "description": "Invoice copy"}
]
""",
        encoding="utf-8",
    )
    result = compare_allowlists_on_ndjson(export, allow, allow)
    assert result.total == 2
    assert result.tbc_old == result.tbc_new


def test_compare_allowlists_on_ndjson(repo_root: Path) -> None:
    ndjson = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not ndjson.is_file():
        pytest.skip("fixture missing")
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, ref)
    result = compare_allowlists_on_ndjson(ndjson, allow, allow)
    assert result.total == 5
    assert result.tbc_old == result.tbc_new
    assert result.tbc_b2b_old == result.tbc_b2b_new
    assert result.tbc_b2c_old == result.tbc_b2c_new
    assert result.tbc_b2b_old + result.tbc_b2c_old <= result.tbc_old
    assert result.zero_candidate_old == result.zero_candidate_new
    assert result.changed_rows == []


def test_compare_allowlists_bad_satisfaction_only(tmp_path: Path, repo_root: Path) -> None:
    import json

    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, ref)
    tickets = [
        {"url": "https://example.zendesk.com/api/v2/tickets/1.json", "id": 1, "tags": ["app"]},
        {
            "url": "https://example.zendesk.com/api/v2/tickets/2.json",
            "id": 2,
            "tags": ["app"],
            "satisfaction_rating": {"score": "bad"},
        },
    ]
    ndjson = tmp_path / "ratings.ndjson"
    ndjson.write_text("\n".join(json.dumps(t) for t in tickets), encoding="utf-8")
    all_rows = compare_allowlists_on_ndjson(ndjson, allow, allow)
    bad_only = compare_allowlists_on_ndjson(ndjson, allow, allow, bad_satisfaction_only=True)
    assert all_rows.total == 2
    assert bad_only.total == 1
    assert bad_only.bad_satisfaction_only is True


def test_session_commit_and_revert(repo_root: Path, tmp_path: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")

    novel = ("RevertSeg", "RevertStream", "RevertCat", "RevertType", "RevertGran")
    allow_before = load_allowlist(tax, ref)
    if novel in allow_before:
        pytest.skip("fixture tuple already in allow-list")

    work_root = tmp_path / "repo"
    doc = work_root / "doc"
    doc.mkdir(parents=True)
    shutil.copy2(tax, doc / "Taxonomy.csv")
    shutil.copy2(ref, doc / "CS_ticket_new_categorizations.xlsx")

    upload = tmp_path / "upload.xlsx"
    _write_workbook(
        upload,
        [
            _sample_row(
                id="99",
                Tier1_Segment=novel[0],
                Tier2_Stream=novel[1],
                Tier3_Cat=novel[2],
                Tier4_Type=novel[3],
                Granular_Tech_UI_Type=novel[4],
            )
        ],
    )

    session = create_session(upload, work_root)
    try:
        result = commit_session(session, frozenset({novel}))
        assert result.rows_added == 1
        assert result.rules_added >= 0
        allow_after = load_allowlist(doc / "Taxonomy.csv", doc / "CS_ticket_new_categorizations.xlsx")
        assert novel in allow_after
        rules_file = doc / "training_rules.json"
        if result.rules_added:
            assert rules_file.is_file()
    finally:
        drop_session(session)

    assert revert_latest_snapshot(work_root)
    allow_reverted = load_allowlist(doc / "Taxonomy.csv", doc / "CS_ticket_new_categorizations.xlsx")
    assert novel not in allow_reverted


def test_training_available_requires_writable_doc(repo_root: Path) -> None:
    if not (repo_root / "doc" / "CS_ticket_new_categorizations.xlsx").is_file():
        pytest.skip("workbook missing")
    assert training_available(repo_root) is True
