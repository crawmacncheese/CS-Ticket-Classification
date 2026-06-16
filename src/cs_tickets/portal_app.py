from __future__ import annotations

import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
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
from cs_tickets.classifier_rules import set_active_rule_specs
from cs_tickets.drive_live_config import try_sync_live_to_drive
from cs_tickets.feedback.parse import LearnParseResult, parse_categorized_workbook
from cs_tickets.feedback.promote import (
    ConfirmResult,
    PromoteError,
    build_candidate_live_config,
    confirm_hybrid_proposals,
    has_revertable_live_backup,
    release_candidate_live_config,
    revert_latest_live_backup,
)
from cs_tickets.portal_learn import (
    learn_process_body_html,
    learn_proposals_html,
    learn_revert_footer_html,
    learn_selection_hash,
)
from cs_tickets.repo_paths import resolve_repo_root
from cs_tickets.runtime_config import (
    ensure_live_bootstrapped,
    invalidate_runtime_cache,
    load_runtime_allowlist,
    load_runtime_rule_specs,
)
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
    REFERENCE_CATEGORIES_PAGE_INTRO,
    REFERENCE_CATEGORIES_PAGE_TITLE,
    TECHNICAL_DETAILS_BODY,
    TECHNICAL_DETAILS_SUMMARY,
    TICKET_PREVIEW_HEADING,
)
from cs_tickets.portal_layout import portal_page_html
from cs_tickets.portal_stats import classify_run_summary_html, tier_stats_table_html
from cs_tickets.portal_trends import (
    dashboard_body_html,
    dashboard_empty_html,
    dashboard_page_html,
)
from cs_tickets.tbc_trends import (
    init_db,
    load_trend_events,
    trends_db_path,
    trends_events_path,
    try_append_portal_snapshot,
)
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


@dataclass
class _LearnRecord:
    result: LearnParseResult
    temp_dir: Path
    upload_path: Path
    status: str = "processed"
    confirm_result: ConfirmResult | None = None
    drive_live_url: str | None = None
    drive_files_uploaded: int | None = None
    drive_error: str | None = None
    drive_skip_reason: str | None = None
    preview_batch_result: object | None = None
    preview_compare_result: object | None = None
    preview_rule_ids: frozenset[str] = frozenset()
    preview_tax_ids: frozenset[str] = frozenset()
    preview_selection_hash: str | None = None
    preview_bad_satisfaction_only: bool = False
    preview_compute_no_op: bool = False


_LEARN_UPLOADS: dict[str, _LearnRecord] = {}


def _drop_learn_upload(upload_id: str) -> None:
    record = _LEARN_UPLOADS.pop(upload_id, None)
    if record is not None and record.temp_dir.is_dir():
        shutil.rmtree(record.temp_dir, ignore_errors=True)


def _learn_error_html(message: str) -> str:
    body = f"""
    <h1 class="page-header">{REFERENCE_CATEGORIES_PAGE_TITLE}</h1>
    <p class="meta drive-warning" role="alert">{_esc(message)}</p>
    <p class="links"><a href="/learn" class="btn">Try again</a></p>
    """
    return portal_page_html(
        title=REFERENCE_CATEGORIES_PAGE_TITLE,
        active="learn",
        body=body,
    )


def _learn_process_page(record: _LearnRecord, upload_id: str) -> str:
    result = record.result
    if record.preview_selection_hash is not None:
        checked_rules = record.preview_rule_ids
        checked_tax = record.preview_tax_ids
    else:
        checked_rules = None
        checked_tax = None
    summary_meta = (
        f"{result.rule_proposal_count} suggested rules · "
        f"{result.taxonomy_proposal_count} new category paths"
    )
    body = learn_process_body_html(
        result,
        upload_id,
        checked_rule_ids=checked_rules,
        checked_tax_ids=checked_tax,
        batch_result=record.preview_batch_result,
        compare_result=record.preview_compare_result,
        preview_stale=False,
        bad_satisfaction_only=record.preview_bad_satisfaction_only,
        compute_no_op=record.preview_compute_no_op,
    )
    page_body = f"""
    <p class="run-summary" role="status">
        <span class="run-summary-lead">{result.row_count} rows parsed</span>
        <span class="run-summary-meta">({summary_meta})</span>
    </p>
    <p class="meta learn-ok">Processed <strong>{_esc(result.filename)}</strong> — upload id <code>{_esc(upload_id)}</code></p>
    <p class="meta">{result.distinct_tier_paths} distinct categories in upload · {result.eligible_row_count} rows used for learning</p>
    {body}
    """
    return portal_page_html(
        title=REFERENCE_CATEGORIES_PAGE_TITLE,
        active="learn",
        body=page_body,
    )


def _repo_root() -> Path:
    return resolve_repo_root()


def _sync_runtime_classifier(repo_root: Path | None = None) -> None:
    root = repo_root or _repo_root()
    ensure_live_bootstrapped(root)
    set_active_rule_specs(load_runtime_rule_specs(root))
    invalidate_runtime_cache()


def _default_allowlist():
    root = _repo_root()
    _sync_runtime_classifier(root)
    allow = load_runtime_allowlist(root)
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
    body = f"""
    <div class="upload-intro">
        <h1 class="page-header">{CLASSIFY_PAGE_TITLE}</h1>
        <p class="meta">{CLASSIFY_PAGE_INTRO}</p>
    </div>
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
    """
    return portal_page_html(
        title=CLASSIFY_PAGE_TITLE,
        active="categorize",
        body_class="upload-page",
        main_class="upload-page",
        extra_scripts=["/static/classify.js"],
        body=body,
    )


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
        trends_snapshot = try_append_portal_snapshot(
            tmp_path,
            allow,
            repo_root=_repo_root(),
            source_filename=source_filename,
            bad_satisfaction_only=bad_satisfaction_only,
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
        trends_html = ""
        if trends_snapshot is not None:
            snap_rows, snap_tbc = trends_snapshot
            snap_pct = f"{100.0 * snap_tbc / snap_rows:.1f}%" if snap_rows else "0.0%"
            trends_html = (
                f'<p class="meta trends-snapshot-ok">'
                f"Added to <a href=\"/dashboard\">TBC trends</a>: "
                f"{snap_rows} tickets ({snap_tbc} manual review, {snap_pct}).</p>"
            )
        run_actions = _classify_run_actions_html(run_id, primary=True)
        body = f"""
    {summary_block}
    {filter_note}
    {trends_html}
    {run_actions}
    {drive_html}
    <p class="download-hint meta">Workbook includes sheets <strong>Run metadata</strong>, <strong>Tickets</strong> (full rows), and <strong>Tier breakdown</strong> (category counts).</p>

    <h2 class="section-header">{CATEGORY_BREAKDOWN_HEADING}</h2>
    <p class="meta">{CATEGORY_BREAKDOWN_META}</p>
    <div class="stats-wrap">{stats_block}</div>

    <h2 class="section-header">{TICKET_PREVIEW_HEADING}</h2>
    <p class="meta">First {len(preview)} rows of the master table.</p>
    <div class="preview-wrap">
        <table class="preview-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{body_rows}</tbody>
        </table>
    </div>

    {_classify_technical_details_html()}
    """
        return portal_page_html(
            title="Categorization results",
            active="categorize",
            body=body,
        )
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


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    root = _repo_root()
    db_path = trends_db_path(root)
    if not db_path.is_file():
        body = dashboard_empty_html(db_path=db_path, repo_root=root)
        return dashboard_page_html(body=body)
    conn = init_db(db_path)
    try:
        events = load_trend_events(trends_events_path(root))
        body = dashboard_body_html(conn, db_path=db_path, events=events)
    finally:
        conn.close()
    return dashboard_page_html(body=body)


def _training_head() -> str:
    from cs_tickets.portal_layout import portal_head

    return portal_head(title="CS Tickets — Training")


def _require_session(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=400, detail="Unknown or expired training session; upload again.")
    return session


def _default_allowlist_paths(root: Path) -> tuple[Path | None, Path | None]:
    tax = root / "doc" / "Taxonomy.csv"
    wb = root / "doc" / "CS_ticket_new_categorizations.xlsx"
    return (tax if tax.is_file() else None, wb if wb.is_file() else None)


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


@app.get("/learn", response_class=HTMLResponse)
def learn_index() -> str:
    root = _repo_root()
    live = ensure_live_bootstrapped(root)
    revert_footer = learn_revert_footer_html(show_revert=has_revertable_live_backup(live))
    body = f"""
    <div class="upload-intro">
        <h1 class="page-header">{REFERENCE_CATEGORIES_PAGE_TITLE}</h1>
        <p class="meta">{REFERENCE_CATEGORIES_PAGE_INTRO}</p>
    </div>
    <div class="upload-card-wrap">
        <div class="upload-card">
            <form class="upload-form" action="/learn/process" method="post" enctype="multipart/form-data">
                <input type="file" name="workbook" class="file-input" accept=".xlsx" required>
                <button type="submit" class="btn btn-primary">Process</button>
            </form>
        </div>
    </div>
    {revert_footer}
    """
    return portal_page_html(
        title=REFERENCE_CATEGORIES_PAGE_TITLE,
        active="learn",
        body_class="upload-page",
        main_class="upload-page",
        body=body,
    )


@app.get("/learn/process")
def learn_process_get() -> RedirectResponse:
    return RedirectResponse(url="/learn", status_code=303)


@app.post("/learn/process", response_class=HTMLResponse)
async def learn_process(workbook: UploadFile = File(...)) -> str:
    upload_id = str(uuid.uuid4())
    source_filename = workbook.filename or "workbook.xlsx"
    suffix = Path(source_filename).suffix.lower()
    if suffix != ".xlsx":
        return _learn_error_html("Upload must be an .xlsx workbook.")

    tmpdir = Path(tempfile.mkdtemp(prefix="cs_tickets_learn_"))
    tmp_path = tmpdir / f"workbook{suffix}"
    tmp_path.write_bytes(await workbook.read())
    repo_root = _repo_root()
    try:
        allow = _default_allowlist()
        existing_rules = load_runtime_rule_specs(repo_root)
        result = parse_categorized_workbook(
            tmp_path,
            upload_id=upload_id,
            filename=source_filename,
            allow=allow,
            existing_rules=existing_rules,
        )
    except ValueError as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return _learn_error_html(str(exc))

    _LEARN_UPLOADS[upload_id] = _LearnRecord(
        result=result,
        temp_dir=tmpdir,
        upload_path=tmp_path,
    )
    return _learn_process_page(_LEARN_UPLOADS[upload_id], upload_id)


@app.get("/learn/preview")
def learn_preview_get() -> RedirectResponse:
    return RedirectResponse(url="/learn", status_code=303)


@app.post("/learn/preview", response_class=HTMLResponse)
async def learn_preview(
    upload_id: str = Form(...),
    rule_ids: list[str] = Form(default=[]),
    tax_ids: list[str] = Form(default=[]),
    preview_file: UploadFile = File(...),
    bad_satisfaction_only: bool = Form(False),
    compute_no_op: bool = Form(False),
) -> str:
    record = _LEARN_UPLOADS.get(upload_id)
    if not record or record.status != "processed":
        return _learn_error_html("Upload session expired or unknown. Process the workbook again.")
    _require_extension(preview_file.filename, _JSON_EXTENSIONS, "Preview file")

    accepted_rules = frozenset(rule_ids)
    accepted_tax = frozenset(tax_ids)
    if not accepted_rules and not accepted_tax:
        return _learn_error_html("Select at least one rule or category path before running preview.")

    repo_root = _repo_root()
    live = ensure_live_bootstrapped(repo_root)
    tmpdir = tempfile.mkdtemp(prefix="cs_learn_preview_")
    suffix = Path(preview_file.filename or "preview.json").suffix.lower() or ".json"
    preview_path = Path(tmpdir) / f"preview_input{suffix}"
    candidate = None
    try:
        preview_path.write_bytes(await preview_file.read())
        candidate = build_candidate_live_config(
            live,
            upload_xlsx=record.upload_path,
            rule_proposals=record.result.rule_proposals,
            taxonomy_proposals=record.result.taxonomy_proposals,
            accepted_rule_ids=accepted_rules,
            accepted_taxonomy_ids=accepted_tax,
        )
        batch_result = run_commit_simulation(
            [preview_path],
            candidate.allow_old,
            candidate.allow_new,
            selected_tuples=candidate.selected_tuples,
            rule_specs_new=candidate.rule_specs_new,
            compute_no_op=compute_no_op,
            bad_satisfaction_only=bad_satisfaction_only,
        )
        record.preview_batch_result = batch_result
        record.preview_compare_result = batch_result.combined
        record.preview_rule_ids = accepted_rules
        record.preview_tax_ids = accepted_tax
        record.preview_selection_hash = learn_selection_hash(accepted_rules, accepted_tax)
        record.preview_bad_satisfaction_only = bad_satisfaction_only
        record.preview_compute_no_op = compute_no_op
        return _learn_process_page(record, upload_id)
    except PromoteError as exc:
        return _learn_error_html(str(exc))
    except ValueError as exc:
        return _learn_error_html(str(exc))
    finally:
        if candidate is not None:
            release_candidate_live_config(candidate)
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.get("/learn/confirm")
def learn_confirm_get() -> RedirectResponse:
    return RedirectResponse(url="/learn", status_code=303)


@app.post("/learn/confirm", response_class=HTMLResponse)
async def learn_confirm(
    upload_id: str = Form(...),
    rule_ids: list[str] = Form(default=[]),
    tax_ids: list[str] = Form(default=[]),
) -> str:
    record = _LEARN_UPLOADS.get(upload_id)
    if not record:
        return _learn_error_html("Upload session expired or unknown. Process the workbook again.")

    if record.status == "live":
        body = f"""
    {learn_proposals_html(
        record.result,
        upload_id,
        status="live",
        confirm_result=record.confirm_result,
        drive_live_url=record.drive_live_url,
        drive_files_uploaded=record.drive_files_uploaded,
        drive_error=record.drive_error,
        drive_skip_reason=record.drive_skip_reason,
    )}
    <p class="links"><a href="/learn" class="btn">Upload another</a></p>
    """
        return portal_page_html(
            title=REFERENCE_CATEGORIES_PAGE_TITLE,
            active="learn",
            body=body,
        )

    repo_root = _repo_root()
    live = ensure_live_bootstrapped(repo_root)
    try:
        confirm_result = confirm_hybrid_proposals(
            live,
            upload_id=upload_id,
            upload_filename=record.result.filename,
            upload_xlsx=record.upload_path,
            rule_proposals=record.result.rule_proposals,
            taxonomy_proposals=record.result.taxonomy_proposals,
            accepted_rule_ids=frozenset(rule_ids),
            accepted_taxonomy_ids=frozenset(tax_ids),
        )
    except PromoteError as exc:
        return _learn_error_html(str(exc))

    _sync_runtime_classifier(repo_root)
    drive_sync, drive_error, drive_skip = try_sync_live_to_drive(
        live,
        proposals_dir=confirm_result.proposals_dir,
        backup_version=confirm_result.config_version_before,
    )
    record.status = "live"
    record.confirm_result = confirm_result
    record.drive_error = drive_error
    record.drive_skip_reason = drive_skip
    record.drive_live_url = drive_sync.live_folder_url if drive_sync else None
    record.drive_files_uploaded = drive_sync.files_uploaded if drive_sync else None
    if record.temp_dir.is_dir():
        shutil.rmtree(record.temp_dir, ignore_errors=True)

    live_after = ensure_live_bootstrapped(repo_root)
    revert_footer = learn_revert_footer_html(show_revert=has_revertable_live_backup(live_after))
    body = f"""
    {learn_proposals_html(
        record.result,
        upload_id,
        status="live",
        confirm_result=confirm_result,
        drive_live_url=record.drive_live_url,
        drive_files_uploaded=record.drive_files_uploaded,
        drive_error=record.drive_error,
        drive_skip_reason=record.drive_skip_reason,
    )}
    <p class="links">
        <a href="/" class="btn btn-primary">{NEW_UPLOAD_LABEL}</a>
        <a href="/learn" class="btn">Upload another</a>
    </p>
    {revert_footer}
    """
    return portal_page_html(
        title=REFERENCE_CATEGORIES_PAGE_TITLE,
        active="learn",
        body=body,
    )


@app.post("/learn/cancel", response_class=RedirectResponse)
async def learn_cancel(upload_id: str = Form(...)) -> RedirectResponse:
    _drop_learn_upload(upload_id)
    return RedirectResponse(url="/learn", status_code=303)


@app.post("/learn/revert", response_class=HTMLResponse)
async def learn_revert() -> str:
    repo_root = _repo_root()
    live = ensure_live_bootstrapped(repo_root)
    try:
        restored_version = revert_latest_live_backup(live)
    except PromoteError as exc:
        return _learn_error_html(str(exc))
    _sync_runtime_classifier(repo_root)
    revert_footer = learn_revert_footer_html(show_revert=has_revertable_live_backup(live))
    body = f"""
    <h1 class="page-header">{REFERENCE_CATEGORIES_PAGE_TITLE}</h1>
    <p class="run-summary" role="status">Restored live config to version {restored_version}.</p>
    <p class="meta">The next categorisation run will use the reverted allow-list and rules.</p>
    <p class="links"><a href="/learn" class="btn">Upload another</a></p>
    {revert_footer}
    """
    return portal_page_html(
        title=REFERENCE_CATEGORIES_PAGE_TITLE,
        active="learn",
        body=body,
    )


@app.get("/training", response_class=RedirectResponse)
def training_redirect_to_learn() -> RedirectResponse:
    return RedirectResponse(url="/learn", status_code=307)
