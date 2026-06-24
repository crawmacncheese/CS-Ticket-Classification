from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cs_tickets import portal_app
from cs_tickets.portal_app import app
from cs_tickets.portal_learn import learn_revert_footer_html

client = TestClient(app)


def test_learn_revert_footer_uses_copy_not_placeholders() -> None:
    html = learn_revert_footer_html(show_revert=True)
    assert "Undo Last Confirm" in html
    assert "Restores the previous live settings" in html
    assert "{LEARN_UNDO" not in html


def test_index_links_to_learn() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/learn"' in r.text
    assert "Add New Categories" in r.text
    assert "portal-topnav" in r.text


def test_learn_index_has_process_form() -> None:
    r = client.get("/learn")
    assert r.status_code == 200
    assert "Add New Categories" in r.text
    assert 'action="/learn/process"' in r.text
    assert "SCMP_Tickets_Master_Categorized" in r.text
    assert 'name="workbook"' in r.text


def test_learn_process_workbook(repo_root: Path) -> None:
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not xlsx.is_file():
        pytest.skip("doc workbook missing")
    portal_app._LEARN_UPLOADS.clear()
    body = xlsx.read_bytes()
    r = client.post(
        "/learn/process",
        files={
            "workbook": (
                "CS_ticket_new_categorizations.xlsx",
                body,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r.status_code == 200
    assert "rows parsed" in r.text
    assert "suggested rules" in r.text.lower()
    assert "When tickets" in r.text
    assert 'class="stats-table"' in r.text
    assert "Confirm changes" in r.text
    assert "Cancel" in r.text
    assert 'formaction="/learn/cancel"' in r.text
    assert "learn-preview-section" in r.text
    assert "Preview: see how this affects real tickets" in r.text
    assert 'class="learn-preview-details"' in r.text
    assert 'aria-label="Learn progress"' in r.text
    assert "Session details" in r.text
    assert 'class="session-details"' in r.text
    assert "any_tags:" not in r.text
    assert "Phase 2 stub" not in r.text
    assert len(portal_app._LEARN_UPLOADS) == 1
    assert 'action="/learn/preview"' in r.text


def test_learn_cancel_drops_session(repo_root: Path) -> None:
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not xlsx.is_file():
        pytest.skip("doc workbook missing")
    portal_app._LEARN_UPLOADS.clear()
    process = client.post(
        "/learn/process",
        files={
            "workbook": (
                "CS_ticket_new_categorizations.xlsx",
                xlsx.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert process.status_code == 200
    upload_id = next(iter(portal_app._LEARN_UPLOADS))
    cancel = client.post("/learn/cancel", data={"upload_id": upload_id}, follow_redirects=False)
    assert cancel.status_code == 303
    assert cancel.headers["location"] == "/learn"
    assert upload_id not in portal_app._LEARN_UPLOADS


def test_learn_preview_ndjson(repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    ndjson = repo_root / "tests" / "fixtures" / "training_tbc_probe.ndjson"
    if not xlsx.is_file() or not ndjson.is_file():
        pytest.skip("fixtures missing")

    target_root = tmp_path / "proj"
    (target_root / "doc").mkdir(parents=True)
    for name in ("Taxonomy.csv", "CS_ticket_new_categorizations.xlsx"):
        src = repo_root / "doc" / name
        if src.is_file():
            (target_root / "doc" / name).write_bytes(src.read_bytes())

    monkeypatch.setenv("CS_TICKETS_REPO_ROOT", str(target_root))
    portal_app._LEARN_UPLOADS.clear()

    process = client.post(
        "/learn/process",
        files={
            "workbook": (
                "CS_ticket_new_categorizations.xlsx",
                xlsx.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert process.status_code == 200
    upload_id = next(iter(portal_app._LEARN_UPLOADS))
    record = portal_app._LEARN_UPLOADS[upload_id]
    if not record.result.rule_proposals and not record.result.taxonomy_proposals:
        pytest.skip("no proposals in fixture run")

    rule_ids = [p.proposal_id for p in record.result.rule_proposals[:1]]
    tax_ids = [p.proposal_id for p in record.result.taxonomy_proposals[:1]]
    if not rule_ids and not tax_ids:
        pytest.skip("no selectable proposals")

    preview = client.post(
        "/learn/preview",
        data={
            "upload_id": upload_id,
            "rule_ids": rule_ids,
            "tax_ids": tax_ids,
        },
        files={
            "preview_file": (
                "training_tbc_probe.ndjson",
                ndjson.read_bytes(),
                "application/x-ndjson",
            )
        },
    )
    assert preview.status_code == 200
    assert "preview results" in preview.text.lower() or "manual review" in preview.text.lower()
    assert record.preview_batch_result is not None


def test_learn_confirm_applies_selected_rules(repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not xlsx.is_file():
        pytest.skip("doc workbook missing")

    target_root = tmp_path / "proj"
    (target_root / "doc").mkdir(parents=True)
    for name in ("Taxonomy.csv", "CS_ticket_new_categorizations.xlsx"):
        src = repo_root / "doc" / name
        if src.is_file():
            (target_root / "doc" / name).write_bytes(src.read_bytes())

    monkeypatch.setenv("CS_TICKETS_REPO_ROOT", str(target_root))
    portal_app._LEARN_UPLOADS.clear()
    from cs_tickets.classifier_rules import set_active_rule_specs

    set_active_rule_specs(None)

    process = client.post(
        "/learn/process",
        files={
            "workbook": (
                "CS_ticket_new_categorizations.xlsx",
                xlsx.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert process.status_code == 200
    upload_id = next(iter(portal_app._LEARN_UPLOADS))
    record = portal_app._LEARN_UPLOADS[upload_id]
    if not record.result.rule_proposals:
        pytest.skip("no rule proposals in fixture run")
    first_rule = record.result.rule_proposals[0].proposal_id

    confirm = client.post(
        "/learn/confirm",
        data={"upload_id": upload_id, "rule_ids": [first_rule]},
    )
    assert confirm.status_code == 200
    assert "Live — config version" in confirm.text
    assert portal_app._LEARN_UPLOADS[upload_id].status == "live"
    live_rules = target_root / "runs" / "live" / "classifier_rules.json"
    assert live_rules.is_file()
    assert first_rule.removeprefix("rule.") in live_rules.read_text(encoding="utf-8")


def test_learn_process_rejects_non_xlsx() -> None:
    r = client.post(
        "/learn/process",
        files={"workbook": ("bad.csv", b"a,b", "text/csv")},
    )
    assert r.status_code == 200
    assert "must be an .xlsx workbook" in r.text


def test_learn_process_get_redirects() -> None:
    r = client.get("/learn/process", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/learn"

