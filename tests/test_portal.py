import re
import shutil
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from cs_tickets import portal_app
from cs_tickets.portal_app import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.text == "ok"


def test_index_has_upload_form() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Categorize support tickets" in r.text
    assert 'action="/run"' in r.text
    assert "bad CSAT rating" in r.text
    assert "/static/classify.js" in r.text
    assert "How categorization works (technical)" in r.text
    assert "readme-doc" not in r.text
    assert "mermaid@10" not in r.text


def test_run_upload_bad_satisfaction_only(repo_root: Path, tmp_path: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("fixtures missing")
    portal_app._RUNS.clear()
    ndjson = (
        '{"url":"https://example.zendesk.com/api/v2/tickets/1.json","id":1,"tags":["app"],'
        '"satisfaction_rating":{"score":"bad"}}\n'
        '{"url":"https://example.zendesk.com/api/v2/tickets/2.json","id":2,"tags":["app"],'
        '"satisfaction_rating":{"score":"good"}}\n'
    )
    r = client.post(
        "/run",
        data={"bad_satisfaction_only": "true"},
        files={"export": ("ratings.ndjson", ndjson.encode(), "application/octet-stream")},
    )
    assert r.status_code == 200
    assert "1 tickets categorized" in r.text
    assert "bad CSAT rating" in r.text


def test_run_upload_ndjson(repo_root: Path) -> None:
    export = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not export.is_file():
        pytest.skip("fixture missing")
    portal_app._RUNS.clear()
    body = export.read_bytes()
    r = client.post(
        "/run",
        files={"export": ("sample.ndjson", body, "application/octet-stream")},
    )
    assert r.status_code == 200
    assert "tickets categorized" in r.text
    assert "manual review" in r.text
    assert "(TBC)" in r.text
    assert "portal-topnav" in r.text
    assert "Download Excel workbook" in r.text
    assert "New upload" in r.text
    assert "Run history" in r.text
    assert "drive.google.com/drive/folders/" in r.text
    assert "Category breakdown" in r.text
    assert "/static/cs_tickets_theme.css" in r.text
    assert "stats-table" in r.text
    assert "Grand Total" in r.text
    assert "readme-doc" not in r.text
    run_id = next(iter(portal_app._RUNS))
    assert f'/download/{run_id}"' in r.text


def test_download_workbook_has_tickets_and_tier_tabs(repo_root: Path) -> None:
    export = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not export.is_file():
        pytest.skip("fixture missing")
    portal_app._RUNS.clear()
    body = export.read_bytes()
    r = client.post(
        "/run",
        files={"export": ("sample.ndjson", body, "application/octet-stream")},
    )
    assert r.status_code == 200
    assert len(portal_app._RUNS) == 1
    run_id = next(iter(portal_app._RUNS))
    d = client.get(f"/download/{run_id}")
    assert d.status_code == 200
    assert "spreadsheetml" in d.headers.get("content-type", "")
    assert d.content[:2] == b"PK"
    wb = load_workbook(BytesIO(d.content), read_only=True, data_only=True)
    assert wb.sheetnames == ["Run metadata", "Tickets", "Tier breakdown"]
    ws = wb["Tier breakdown"]
    tier_rows = list(ws.iter_rows(min_row=1, max_col=5, values_only=True))
    assert tier_rows[0][0] == "Tier1_Segment"
    assert tier_rows[0][4] == "COUNTA of id"
    assert tier_rows[-1][0] == "Grand Total"
    assert isinstance(tier_rows[-1][4], int)
    assert tier_rows[-1][4] == 5


def test_run_upload_invalid_json_returns_400() -> None:
    r = client.post(
        "/run",
        files={"export": ("bad.json", b"not json at all", "application/octet-stream")},
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "Could not parse" in detail or "No JSON ticket" in detail
def test_run_upload_shows_drive_link_when_upload_succeeds(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    export = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not export.is_file():
        pytest.skip("fixture missing")
    from cs_tickets.drive_upload import DriveUploadResult

    monkeypatch.setenv("DRIVE_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_DRIVE_RUNS_FOLDER_ID", "folder-test")
    monkeypatch.setattr(
        "cs_tickets.portal_app.try_upload_workbook",
        lambda _payload, *, filename: (
            DriveUploadResult(
                file_id="abc",
                filename=filename,
                web_view_link="https://drive.google.com/file/d/abc/view",
            ),
            None,
        ),
    )
    body = export.read_bytes()
    r = client.post(
        "/run",
        files={"export": ("sample.ndjson", body, "application/octet-stream")},
    )
    assert r.status_code == 200
    assert "Saved to Google Drive" in r.text
    assert "drive.google.com" in r.text


def test_static_theme_css() -> None:
    r = client.get("/static/cs_tickets_theme.css")
    assert r.status_code == 200
    assert "stats-table" in r.text
    assert r.headers.get("content-type", "").startswith("text/css")


def test_training_link_on_index_when_available(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cs_tickets.portal_app._repo_root", lambda: repo_root)
    r = client.get("/")
    assert r.status_code == 200
    assert "/learn" in r.text
    assert "Update reference categories" in r.text
    assert "portal-topnav" in r.text


def test_training_redirects_to_learn() -> None:
    r = client.get("/training", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/learn"


def test_training_hidden_when_not_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cs_tickets.portal_app.training_available", lambda _root: False)
    r = client.post("/training/upload", files={"workbook": ("x.xlsx", b"", "application/octet-stream")})
    assert r.status_code == 404


def test_training_upload_via_post(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cs_tickets.portal_app._repo_root", lambda: repo_root)
    monkeypatch.setattr("cs_tickets.portal_app.training_available", lambda _root: True)
    r = client.get("/training", follow_redirects=True)
    assert r.status_code == 200
    assert "Update reference categories" in r.text


def _training_sample_row(**tier_overrides: str) -> dict[str, str]:
    from cs_tickets.schema import MASTER_COLUMNS, TIER_COLUMNS

    row = {c: "" for c in MASTER_COLUMNS}
    row["id"] = tier_overrides.pop("id", "1")
    row["subject"] = tier_overrides.pop("subject", "Test ticket")
    for col in TIER_COLUMNS:
        row[col] = tier_overrides.get(col, "Fill")
    return row


def _write_training_workbook(path: Path, rows: list[dict[str, str]]) -> None:
    from openpyxl import Workbook
    from cs_tickets.schema import MASTER_COLUMNS

    wb = Workbook()
    ws = wb.active
    ws.title = "SCMP_Tickets_Master_Categorized"
    ws.append(list(MASTER_COLUMNS))
    for row in rows:
        ws.append([row.get(c, "") for c in MASTER_COLUMNS])
    wb.save(path)


def test_training_preview_uses_candidate_allowlist_without_commit(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cs_tickets.allowlist_training import drop_session, get_session
    from cs_tickets.taxonomy import load_allowlist

    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")

    novel = ("PortalPrevSeg", "PortalPrevStream", "PortalPrevCat", "PortalPrevType", "PortalPrevGran")
    allow_before = load_allowlist(tax, ref)
    if novel in allow_before:
        pytest.skip("fixture tuple already in allow-list")

    upload = tmp_path / "upload.xlsx"
    _write_training_workbook(
        upload,
        [
            _training_sample_row(
                id="99",
                subject="Account login reset help",
                Tier1_Segment=novel[0],
                Tier2_Stream=novel[1],
                Tier3_Cat=novel[2],
                Tier4_Type=novel[3],
                Granular_Tech_UI_Type=novel[4],
            )
        ],
    )

    monkeypatch.setattr("cs_tickets.portal_app._repo_root", lambda: repo_root)
    monkeypatch.setattr("cs_tickets.portal_app.training_available", lambda _root: True)

    upload_r = client.post(
        "/training/upload",
        files={
            "workbook": (
                "upload.xlsx",
                upload.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_r.status_code == 200
    m = re.search(r'name="session_id" value="([^"]+)"', upload_r.text)
    assert m
    session_id = m.group(1)

    ndjson = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not ndjson.is_file():
        pytest.skip("fixture missing")

    encoded = "|".join(novel)
    preview_r = client.post(
        "/training/preview",
        data={
            "session_id": session_id,
            "selected_tuple": [encoded],
        },
        files={
            "preview_file": (
                "five_tickets.ndjson",
                ndjson.read_bytes(),
                "application/octet-stream",
            )
        },
    )
    assert preview_r.status_code == 200, preview_r.text[:500]
    assert "training-wizard" in preview_r.text
    assert "verdict-banner" in preview_r.text
    assert "Reference categories (pending save)" in preview_r.text
    assert "B2B manual review (TBC)" in preview_r.text
    assert "B2C manual review (TBC)" in preview_r.text
    assert re.search(
        r"Reference categories \(pending save\)</td><td>\d+</td><td>\d+</td><td>\+\d+</td>",
        preview_r.text,
    )
    assert "Category path" in preview_r.text
    assert "Only preview tickets with bad CSAT rating" in preview_r.text
    assert "Check which categories have no impact" in preview_r.text
    assert 'name="compute_no_op"' in preview_r.text

    allow_after_disk = load_allowlist(tax, ref)
    assert novel not in allow_after_disk
    assert len(allow_after_disk.tuples) == len(allow_before.tuples)

    session = get_session(session_id)
    if session:
        drop_session(session)


def test_training_preview_bad_satisfaction_only(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cs_tickets.allowlist_training import drop_session, get_session
    from cs_tickets.taxonomy import load_allowlist

    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")

    novel = ("PortalBadSeg", "PortalBadStream", "PortalBadCat", "PortalBadType", "PortalBadGran")
    allow_before = load_allowlist(tax, ref)
    if novel in allow_before:
        pytest.skip("fixture tuple already in allow-list")

    upload = tmp_path / "upload.xlsx"
    _write_training_workbook(
        upload,
        [
            _training_sample_row(
                id="99",
                subject="Account login reset help",
                Tier1_Segment=novel[0],
                Tier2_Stream=novel[1],
                Tier3_Cat=novel[2],
                Tier4_Type=novel[3],
                Granular_Tech_UI_Type=novel[4],
            )
        ],
    )

    monkeypatch.setattr("cs_tickets.portal_app._repo_root", lambda: repo_root)
    monkeypatch.setattr("cs_tickets.portal_app.training_available", lambda _root: True)

    upload_r = client.post(
        "/training/upload",
        files={
            "workbook": (
                "upload.xlsx",
                upload.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_r.status_code == 200
    m = re.search(r'name="session_id" value="([^"]+)"', upload_r.text)
    assert m
    session_id = m.group(1)

    ndjson = (
        '{"url":"https://example.zendesk.com/api/v2/tickets/1.json","id":1,"tags":["app"]}\n'
        '{"url":"https://example.zendesk.com/api/v2/tickets/2.json","id":2,"tags":["app"],'
        '"satisfaction_rating":{"score":"bad"}}\n'
    )
    encoded = "|".join(novel)
    preview_r = client.post(
        "/training/preview",
        data={
            "session_id": session_id,
            "selected_tuple": [encoded],
            "bad_satisfaction_only": "true",
        },
        files={
            "preview_file": (
                "ratings.ndjson",
                ndjson.encode(),
                "application/octet-stream",
            )
        },
    )
    assert preview_r.status_code == 200, preview_r.text[:500]
    assert "Preview limited to tickets with bad CSAT rating" in preview_r.text
    assert re.search(r"Total tickets</td><td>1</td><td>1</td>", preview_r.text)

    session = get_session(session_id)
    assert session is not None
    assert session.preview_bad_satisfaction_only is True
    drop_session(session)


def test_training_commit_without_preview_file(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cs_tickets.allowlist_training import drop_session, get_session
    from cs_tickets.taxonomy import load_allowlist

    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")

    novel = ("CommitOnlySeg", "CommitOnlyStream", "CommitOnlyCat", "CommitOnlyType", "CommitOnlyGran")
    allow_before = load_allowlist(tax, ref)
    if novel in allow_before:
        pytest.skip("fixture tuple already in allow-list")

    work_root = tmp_path / "repo"
    doc = work_root / "doc"
    doc.mkdir(parents=True)
    shutil.copy2(tax, doc / "Taxonomy.csv")
    shutil.copy2(ref, doc / "CS_ticket_new_categorizations.xlsx")

    upload = tmp_path / "upload.xlsx"
    _write_training_workbook(
        upload,
        [
            _training_sample_row(
                id="88",
                Tier1_Segment=novel[0],
                Tier2_Stream=novel[1],
                Tier3_Cat=novel[2],
                Tier4_Type=novel[3],
                Granular_Tech_UI_Type=novel[4],
            )
        ],
    )

    monkeypatch.setattr("cs_tickets.portal_app._repo_root", lambda: work_root)
    monkeypatch.setattr("cs_tickets.portal_app.training_available", lambda _root: True)

    upload_r = client.post(
        "/training/upload",
        files={
            "workbook": (
                "upload.xlsx",
                upload.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_r.status_code == 200
    m = re.search(r'name="session_id" value="([^"]+)"', upload_r.text)
    assert m
    session_id = m.group(1)

    encoded = "|".join(novel)
    commit_r = client.post(
        "/training/commit",
        data={"session_id": session_id, "selected_tuple": [encoded]},
    )
    assert commit_r.status_code == 200, commit_r.text[:500]
    assert "Saved 1 category" in commit_r.text

    allow_after = load_allowlist(doc / "Taxonomy.csv", doc / "CS_ticket_new_categorizations.xlsx")
    assert novel in allow_after
    assert len(allow_after.tuples) == len(allow_before.tuples) + 1

    session = get_session(session_id)
    if session:
        drop_session(session)


def test_training_no_new_tuples_shows_done_and_back(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cs_tickets.allowlist_training import drop_session, get_session
    from cs_tickets.taxonomy import load_allowlist

    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")

    allow = load_allowlist(tax, ref)
    existing = next(iter(allow.tuples))
    upload = tmp_path / "upload.xlsx"
    _write_training_workbook(
        upload,
        [
            _training_sample_row(
                id="1",
                Tier1_Segment=existing[0],
                Tier2_Stream=existing[1],
                Tier3_Cat=existing[2],
                Tier4_Type=existing[3],
                Granular_Tech_UI_Type=existing[4],
            )
        ],
    )

    monkeypatch.setattr("cs_tickets.portal_app._repo_root", lambda: repo_root)
    monkeypatch.setattr("cs_tickets.portal_app.training_available", lambda _root: True)

    upload_r = client.post(
        "/training/upload",
        files={
            "workbook": (
                "upload.xlsx",
                upload.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_r.status_code == 200
    assert "No new categories found" in upload_r.text
    assert 'formaction="/training/cancel"' in upload_r.text
    assert "Back to categorize" in upload_r.text
    assert "training-preview-form" not in upload_r.text

    m = re.search(r'name="session_id" value="([^"]+)"', upload_r.text)
    if m:
        session = get_session(m.group(1))
        if session:
            drop_session(session)


def test_run_upload_rejects_txt_extension() -> None:
    r = client.post(
        "/run",
        files={"export": ("export.txt", b'{"id": 1}\n', "text/plain")},
    )
    assert r.status_code == 400
    assert "Export file must be one of" in r.json().get("detail", "")


def test_training_upload_rejects_non_xlsx(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cs_tickets.portal_app._repo_root", lambda: repo_root)
    monkeypatch.setattr("cs_tickets.portal_app.training_available", lambda _root: True)
    r = client.post(
        "/training/upload",
        files={"workbook": ("upload.csv", b"a,b\n1,2", "text/csv")},
    )
    assert r.status_code == 400
    assert "Classified workbook must be one of" in r.json().get("detail", "")


def test_training_preview_rejects_xlsx(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cs_tickets.allowlist_training import drop_session, get_session

    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")

    upload = tmp_path / "upload.xlsx"
    _write_training_workbook(upload, [_training_sample_row(id="1")])

    monkeypatch.setattr("cs_tickets.portal_app._repo_root", lambda: repo_root)
    monkeypatch.setattr("cs_tickets.portal_app.training_available", lambda _root: True)

    upload_r = client.post(
        "/training/upload",
        files={
            "workbook": (
                "upload.xlsx",
                upload.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_r.status_code == 200
    m = re.search(r'name="session_id" value="([^"]+)"', upload_r.text)
    assert m
    session_id = m.group(1)

    preview_r = client.post(
        "/training/preview",
        data={"session_id": session_id, "selected_tuple": ["A|B|C|D|E"]},
        files={
            "preview_file": (
                "preview.xlsx",
                upload.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert preview_r.status_code == 400
    assert "Preview file must be one of" in preview_r.json().get("detail", "")

    session = get_session(session_id)
    if session:
        drop_session(session)
