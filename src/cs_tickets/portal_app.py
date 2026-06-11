from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from starlette.staticfiles import StaticFiles

from cs_tickets.allowlist_training import (
    build_candidate_allowlist,
    build_candidate_rule_set,
    commit_success_message,
    create_session,
    drop_session,
    get_session,
    has_revertable_snapshot,
    revert_latest_snapshot,
    store_preview,
    training_available,
    commit_session,
)
from cs_tickets.repo_paths import resolve_repo_root
from cs_tickets.drive_upload import (
    DriveUploadResult,
    drive_runs_folder_url,
    drive_upload_configured,
    try_upload_workbook,
)
from cs_tickets.pipeline import iter_master_rows
from cs_tickets.portal_copy import (
    CATEGORY_BREAKDOWN_HEADING,
    CATEGORY_BREAKDOWN_META,
    CLASSIFY_BAD_CSAT_LABEL,
    CLASSIFY_PAGE_INTRO,
    CLASSIFY_PAGE_TITLE,
    CLASSIFY_RUN_BUTTON,
    CLASSIFY_RUN_LOADING,
    DOWNLOAD_WORKBOOK_LABEL,
    NEW_UPLOAD_LABEL,
    TECHNICAL_DETAILS_BODY,
    TECHNICAL_DETAILS_SUMMARY,
    TICKET_PREVIEW_HEADING,
    TRAINING_LINK_HINT,
    TRAINING_LINK_LABEL,
)
from cs_tickets.portal_stats import classify_run_summary_html, tier_stats_table_html
from cs_tickets.portal_workbook import build_run_workbook_bytes
from cs_tickets.batch_allowlist_analysis import run_commit_simulation
from cs_tickets.portal_training import (
    REVIEW_STEP_HEADING,
    TRAINING_CANCEL_TITLE,
    TRAINING_REVERT_TITLE,
    TRAINING_REVIEW_TITLE,
    TRAINING_SUCCESS_TITLE,
    TRAINING_TITLE,
    parse_selected_tuples,
    review_intro_html,
    training_checklist_html,
    training_footer_html,
    training_page_shell,
    training_preview_section_html,
    training_upload_body_html,
)
from cs_tickets.run_metadata import build_run_metadata, build_workbook_filename
from cs_tickets.schema import MASTER_COLUMNS
from cs_tickets.taxonomy import load_allowlist

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_JSON_EXTENSIONS = frozenset({".json", ".ndjson"})
_XLSX_EXTENSIONS = frozenset({".xlsx"})


def _require_extension(filename: str | None, allowed: frozenset[str], label: str) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed:
        allowed_list = ", ".join(sorted(allowed))
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be one of: {allowed_list}",
        )

app = FastAPI(title="CS Tickets — local test portal", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

@dataclass
class _RunRecord:
    rows: list[dict]
    source_filename: str
    warns: int
    workbook_filename: str
    drive: DriveUploadResult | None = None
    drive_error: str | None = None


_RUNS: dict[str, _RunRecord] = {}


def _html_head(*, title: str) -> str:
    return f"""<meta charset="utf-8">
    <title>{title}</title>
    <link rel="stylesheet" href="/static/agent_theme_1.css">
    <link rel="stylesheet" href="/static/cs_tickets_theme.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&amp;family=JetBrains+Mono:wght@400&amp;family=Playfair+Display:wght@700&amp;display=swap" rel="stylesheet">"""


def _repo_root() -> Path:
    return resolve_repo_root()


def _default_allowlist():
    root = _repo_root()
    tax = root / "doc" / "Taxonomy.csv"
    wb = root / "doc" / "CS_ticket_new_categorizations.xlsx"
    allow = load_allowlist(
        tax if tax.is_file() else None,
        wb if wb.is_file() else None,
    )
    if len(allow.tuples) <= 5:
        logger.warning(
            "Allow-list is very small (%s tuples); doc/ may be missing on the server. "
            "Set CS_TICKETS_REPO_ROOT to the app root that contains doc/, or ensure "
            "cwd / HOME/site/wwwroot includes Taxonomy.csv and the reference xlsx.",
            len(allow.tuples),
        )
    return allow


def _classify_technical_details_html() -> str:
    return f"""
    <details class="technical-details">
        <summary>{TECHNICAL_DETAILS_SUMMARY}</summary>
        <div class="technical-details-body meta">{TECHNICAL_DETAILS_BODY}</div>
    </details>"""


def _classify_run_actions_html(run_id: str, *, primary: bool = False) -> str:
    primary_cls = " btn-primary" if primary else " btn-secondary"
    return f"""
    <p class="run-actions">
        <a href="/download/{_esc(run_id)}" class="btn{primary_cls}">{DOWNLOAD_WORKBOOK_LABEL}</a>
        <a href="/" class="btn btn-secondary">{NEW_UPLOAD_LABEL}</a>
        <a href="{_esc(drive_runs_folder_url())}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary">Run history</a>
    </p>"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    root = _repo_root()
    training_link = ""
    if training_available(root):
        training_link = f"""
        <p class="links training-entry-link">
            <a href="/training" class="btn btn-primary">{TRAINING_LINK_LABEL}</a>
            <span class="meta training-entry-hint">{TRAINING_LINK_HINT}</span>
        </p>"""
    head = _html_head(title=CLASSIFY_PAGE_TITLE)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>{head}
<script src="/static/classify.js" defer></script>
</head>
<body class="upload-page">
<div class="container upload-page">
    <div class="upload-intro">
        <h1 class="page-header">{CLASSIFY_PAGE_TITLE}</h1>
        <p class="meta">{CLASSIFY_PAGE_INTRO}</p>
    </div>
    {training_link}
    <div class="upload-card-wrap">
        <div class="upload-card">
            <form class="upload-form" action="/run" method="post" enctype="multipart/form-data" data-loading-form>
                <input type="file" name="export" class="file-input" accept=".json,.ndjson" required>
                <label class="filter-option">
                    <input type="checkbox" name="bad_satisfaction_only" value="true">
                    {CLASSIFY_BAD_CSAT_LABEL}
                </label>
                <button type="submit" class="btn btn-primary" data-loading-btn data-loading-label="{CLASSIFY_RUN_LOADING}">{CLASSIFY_RUN_BUTTON}</button>
            </form>
        </div>
    </div>
    {_classify_technical_details_html()}
</div>
</body></html>"""


@app.post("/run", response_class=HTMLResponse)
async def run_upload(
    export: UploadFile = File(...),
    bad_satisfaction_only: bool = Form(False),
) -> str:
    _require_extension(export.filename, _JSON_EXTENSIONS, "Export file")
    allow = _default_allowlist()
    suffix = Path(export.filename or "export.json").suffix or ".json"
    tmpdir = tempfile.mkdtemp(prefix="cs_tickets_")
    tmp_path = Path(tmpdir) / f"export{suffix}"
    try:
        data = await export.read()
        tmp_path.write_bytes(data)
        rows: list[dict] = []
        warns = 0
        try:
            for row, warn in iter_master_rows(
                tmp_path,
                allow,
                bad_satisfaction_only=bad_satisfaction_only,
            ):
                if warn:
                    warns += 1
                rows.append({k: row.get(k) for k in MASTER_COLUMNS})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        run_id = str(uuid.uuid4())
        source_filename = export.filename or "export.json"
        meta = build_run_metadata(
            run_id=run_id,
            source_filename=source_filename,
            rows=rows,
            warning_count=warns,
            bad_satisfaction_only=bad_satisfaction_only,
        )
        workbook_filename = build_workbook_filename(
            source_filename=source_filename,
            run_id=run_id,
        )
        workbook_bytes = build_run_workbook_bytes(rows, metadata=meta)
        drive_result, drive_error = try_upload_workbook(
            workbook_bytes,
            filename=workbook_filename,
        )
        _RUNS[run_id] = _RunRecord(
            rows=rows,
            source_filename=source_filename,
            warns=warns,
            workbook_filename=workbook_filename,
            drive=drive_result,
            drive_error=drive_error,
        )
        preview = rows[:200]
        stats_block = tier_stats_table_html(rows)
        headers = "".join(f"<th>{h}</th>" for h in MASTER_COLUMNS)
        body_rows = ""
        for r in preview:
            body_rows += "<tr>" + "".join(f"<td>{_esc(r.get(h))}</td>" for h in MASTER_COLUMNS) + "</tr>"
        drive_html = _drive_result_html(drive_result, drive_error)
        filter_note = ""
        if bad_satisfaction_only:
            filter_note = '<p class="meta run-filter-note">This run included only tickets with a bad CSAT rating.</p>'
        summary_block = classify_run_summary_html(rows, warns=warns)
        run_actions = _classify_run_actions_html(run_id, primary=True)
        head = _html_head(title="Categorization results")
        return f"""<!DOCTYPE html>
<html lang="en">
<head>{head}</head>
<body>
<div class="container">
    {summary_block}
    {filter_note}
    {run_actions}
    {drive_html}
    <p class="download-hint meta">Workbook includes sheets <strong>Run metadata</strong>, <strong>Tickets</strong> (full rows), and <strong>Tier breakdown</strong> (category counts).</p>

    <h2 class="section-header">{CATEGORY_BREAKDOWN_HEADING}</h2>
    <p class="meta">{CATEGORY_BREAKDOWN_META}</p>
    <div class="stats-wrap">{stats_block}</div>

    {_classify_run_actions_html(run_id, primary=True)}

    <h2 class="section-header">{TICKET_PREVIEW_HEADING}</h2>
    <p class="meta">First {len(preview)} rows of the master table.</p>
    <div class="preview-wrap">
        <table class="preview-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{body_rows}</tbody>
        </table>
    </div>

    {_classify_technical_details_html()}
</div>
</body></html>"""
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _esc(v: object) -> str:
    if v is None:
        return ""
    s = str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s[:500]


def _drive_result_html(
    drive: DriveUploadResult | None,
    drive_error: str | None,
) -> str:
    if drive and drive.web_view_link:
        return (
            f'<p class="meta drive-ok">Saved to Google Drive: '
            f'<a href="{_esc(drive.web_view_link)}" target="_blank" rel="noopener noreferrer">'
            f"{_esc(drive.filename)}</a></p>"
        )
    if drive and not drive.web_view_link:
        return (
            f'<p class="meta drive-ok">Saved to Google Drive as '
            f"<code>{_esc(drive.filename)}</code> (file id {_esc(drive.file_id)}).</p>"
        )
    if drive_error and drive_upload_configured():
        return f'<p class="meta drive-warning">Google Drive upload failed: {_esc(drive_error)}</p>'
    return ""


@app.get("/download/{run_id}")
def download(run_id: str) -> Response:
    record = _RUNS.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Unknown or expired run_id")
    meta = build_run_metadata(
        run_id=run_id,
        source_filename=record.source_filename,
        rows=record.rows,
        warning_count=record.warns,
    )
    payload = build_run_workbook_bytes(record.rows, metadata=meta)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{record.workbook_filename}"',
        },
    )


@app.get("/health")
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")


def _training_head() -> str:
    return _html_head(title="CS Tickets — Training")


def _require_session(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Unknown or expired training session; upload again.")
    return session


def _default_allowlist_paths(root: Path) -> tuple[Path | None, Path | None]:
    tax = root / "doc" / "Taxonomy.csv"
    wb = root / "doc" / "CS_ticket_new_categorizations.xlsx"
    return (tax if tax.is_file() else None, wb if wb.is_file() else None)


@app.get("/training", response_class=HTMLResponse)
def training_index() -> str:
    root = _repo_root()
    if not training_available(root):
        raise HTTPException(status_code=404, detail="Training is not available (doc/ or workbook not writable).")
    body = training_upload_body_html(show_revert=has_revertable_snapshot(root))
    return training_page_shell(
        title=TRAINING_TITLE,
        head=_training_head(),
        body=body,
        wizard_step=1,
    )


@app.post("/training/upload", response_class=HTMLResponse)
async def training_upload(workbook: UploadFile = File(...)) -> str:
    root = _repo_root()
    if not training_available(root):
        raise HTTPException(status_code=404, detail="Training is not available.")
    _require_extension(workbook.filename, _XLSX_EXTENSIONS, "Classified workbook")
    suffix = Path(workbook.filename or "upload.xlsx").suffix or ".xlsx"
    tmpdir = tempfile.mkdtemp(prefix="cs_training_upload_")
    tmp_path = Path(tmpdir) / f"upload{suffix}"
    try:
        tmp_path.write_bytes(await workbook.read())
        try:
            session = create_session(tmp_path, root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _training_review_page(session, selected=frozenset(), preview_result=None)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _training_review_page(
    session,
    *,
    selected,
    preview_result,
    batch_result=None,
) -> str:
    root = session.repo_root
    tax_path, wb_path = _default_allowlist_paths(root)
    allow = load_allowlist(tax_path, wb_path)
    checklist = training_checklist_html(session, selected, allow=allow)
    preview_block = training_preview_section_html(
        session,
        selected,
        preview_result,
        batch_result=batch_result,
    )
    intro = review_intro_html(len(session.new_tuples)) if session.new_tuples else ""
    step_heading = f'<h2 class="section-header">{REVIEW_STEP_HEADING}</h2>' if session.new_tuples else ""
    has_preview = preview_result is not None or batch_result is not None or session.preview_result is not None
    if not session.new_tuples:
        wizard_step = 1
    elif has_preview:
        wizard_step = 3
    else:
        wizard_step = 2
    body = f"""
    {intro}
    {step_heading}
    {checklist}
    {preview_block}
    {training_footer_html(show_revert=has_revertable_snapshot(root), show_back=not session.new_tuples)}
    """
    return training_page_shell(
        title=TRAINING_REVIEW_TITLE,
        head=_training_head(),
        body=body,
        wizard_step=wizard_step,
    )


@app.post("/training/preview", response_class=HTMLResponse)
async def training_preview(
    session_id: str = Form(...),
    selected_tuple: list[str] = Form(default=[]),
    preview_file: UploadFile = File(...),
    bad_satisfaction_only: bool = Form(False),
    compute_no_op: bool = Form(False),
) -> str:
    root = _repo_root()
    if not training_available(root):
        raise HTTPException(status_code=404, detail="Training is not available.")
    session = _require_session(session_id)
    _require_extension(preview_file.filename, _JSON_EXTENSIONS, "Preview file")
    selected = parse_selected_tuples(selected_tuple)
    if not selected:
        raise HTTPException(status_code=400, detail="Select at least one tuple before running preview.")

    tax_path, wb_path = _default_allowlist_paths(root)
    allow_old = load_allowlist(tax_path, wb_path)
    allow_new, merged = build_candidate_allowlist(session, selected)
    if merged == 0:
        raise HTTPException(
            status_code=400,
            detail="Selected combinations did not change the candidate allow-list. Ensure each selected tuple has a matching row in your upload.",
        )

    tmpdir = tempfile.mkdtemp(prefix="cs_training_preview_")
    suffix = Path(preview_file.filename or "preview.json").suffix.lower() or ".json"
    preview_path = Path(tmpdir) / f"preview_input{suffix}"
    try:
        preview_path.write_bytes(await preview_file.read())

        rule_specs_new = build_candidate_rule_set(session, selected)
        try:
            batch_result = run_commit_simulation(
                [preview_path],
                allow_old,
                allow_new,
                selected_tuples=selected,
                rule_specs_new=rule_specs_new,
                compute_no_op=compute_no_op,
                bad_satisfaction_only=bad_satisfaction_only,
            )
            result = batch_result.combined
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store_preview(
            session,
            result,
            selected,
            bad_satisfaction_only=bad_satisfaction_only,
            compute_no_op=compute_no_op,
            batch_result=batch_result,
        )
        return _training_review_page(
            session,
            selected=selected,
            preview_result=result,
            batch_result=batch_result,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/training/commit", response_class=HTMLResponse)
async def training_commit(
    session_id: str = Form(...),
    selected_tuple: list[str] = Form(default=[]),
) -> str:
    root = _repo_root()
    if not training_available(root):
        raise HTTPException(status_code=404, detail="Training is not available.")
    session = _require_session(session_id)
    selected = parse_selected_tuples(selected_tuple)
    if not selected:
        raise HTTPException(status_code=400, detail="Select at least one tuple to commit.")
    result = commit_session(session, selected)
    body = f"""
    <p class="run-summary" role="status">{commit_success_message(result)}</p>
    <p class="meta">Review changes with <code>git diff doc/</code> and commit to version control separately. Training commit writes to disk only.</p>
    <p class="links"><a href="/training" class="btn">New training upload</a></p>
    {training_footer_html(show_revert=True)}
    """
    return training_page_shell(
        title=TRAINING_SUCCESS_TITLE,
        head=_training_head(),
        body=body,
        wizard_step=3,
    )


@app.post("/training/cancel", response_class=HTMLResponse)
async def training_cancel(session_id: str = Form(...)) -> str:
    session = get_session(session_id)
    if session:
        drop_session(session)
    return training_page_shell(
        title=TRAINING_CANCEL_TITLE,
        head=_training_head(),
        body=f"""
        <p class="meta" role="status">Session cancelled — no changes were made to doc/.</p>
        <p class="links"><a href="/training" class="btn">Start over</a></p>
        {training_footer_html(show_revert=has_revertable_snapshot(_repo_root()))}
        """,
        wizard_step=1,
    )


@app.post("/training/revert", response_class=HTMLResponse)
async def training_revert() -> str:
    root = _repo_root()
    if not training_available(root):
        raise HTTPException(status_code=404, detail="Training is not available.")
    if not revert_latest_snapshot(root):
        raise HTTPException(status_code=400, detail="No snapshot available to revert.")
    return training_page_shell(
        title=TRAINING_REVERT_TITLE,
        head=_training_head(),
        body=f"""
        <p class="run-summary" role="status">Restored doc/ artifacts from the latest Training snapshot.</p>
        <p class="meta">If you already committed workbook changes to git, disk may now differ from git history — reconcile manually.</p>
        <p class="links"><a href="/training" class="btn">Training home</a></p>
        {training_footer_html(show_revert=has_revertable_snapshot(root))}
        """,
        wizard_step=1,
    )
