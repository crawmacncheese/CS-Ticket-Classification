from __future__ import annotations

import json
import html
import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.staticfiles import StaticFiles

from cs_tickets.batch_allowlist_analysis import run_commit_simulation
from cs_tickets.allowlist_training import (
    commit_success_message,
    commit_tbc_exemplar,
    training_available,
)
from cs_tickets.classifier_rules import set_active_rule_specs
from cs_tickets.drive_live_config import try_sync_live_to_drive
from cs_tickets.feedback.parse import LearnParseResult, parse_categorized_workbook
from cs_tickets.feedback.promote import (
    ConfirmResult,
    PromoteError,
    build_candidate_live_config,
    confirm_explicit_rule,
    confirm_explicit_rules_batch,
    confirm_hybrid_proposals,
    disable_explicit_rule,
    has_revertable_live_backup,
    release_candidate_live_config,
    revert_latest_live_backup,
)
from cs_tickets.portal_learn import (
    learn_process_body_html,
    learn_proposals_html,
    learn_revert_footer_html,
    learn_selection_hash,
    learn_session_details_html,
    learn_wizard_html,
)
from cs_tickets.repo_paths import resolve_repo_root
from cs_tickets.portal_rules import (
    build_rule_prefill,
    parse_rule_json,
    preview_rule_on_rows,
    rules_editor_html,
    rules_list_html,
)
from cs_tickets.rule_compile import compile_rule_message, compile_result_to_api_dict
from cs_tickets.runtime_config import (
    current_config_version,
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
from cs_tickets.pipeline import iter_master_rows, iter_master_rows_with_meta
from cs_tickets.portal_classify_context import quote_snippet
from cs_tickets.portal_copy import (
    CATEGORY_AUDIT_BUTTON,
    CATEGORY_BREAKDOWN_HEADING,
    CATEGORY_BREAKDOWN_META,
    CLASSIFY_BAD_CSAT_LABEL,
    CLASSIFY_PAGE_INTRO,
    CLASSIFY_PAGE_TITLE,
    CLASSIFY_RUN_BUTTON,
    CLASSIFY_RUN_LOADING,
    DOWNLOAD_WORKBOOK_LABEL,
    LEARN_PROCESS_BUTTON,
    LEARN_TRY_AGAIN_LABEL,
    LEARN_UPLOAD_ANOTHER_LABEL,
    NAV_RUN_HISTORY,
    NAV_TBC_TRENDS,
    NEW_UPLOAD_LABEL,
    REFERENCE_CATEGORIES_PAGE_INTRO,
    REFERENCE_CATEGORIES_PAGE_TITLE,
    RULES_NEW_BUTTON,
    RULES_PAGE_INTRO,
    RULES_PAGE_TITLE,
    TBC_QUEUE_BUTTON,
    TBC_QUEUE_PAGE_TITLE,
    TECHNICAL_DETAILS_BODY,
    TECHNICAL_DETAILS_SUMMARY,
    TICKET_PREVIEW_HEADING,
)
from cs_tickets.category_audit_filters import CategoryAuditFilter
from cs_tickets.category_audit_export import category_audit_slice_csv_bytes
from cs_tickets.category_suggest import suggest_category_for_ticket, suggest_result_to_api_dict
from cs_tickets.category_audit_sweeps import run_category_audit_sweeps
from cs_tickets.portal_category_audit import (
    DEFAULT_CHUNK_SIZE,
    build_category_audit_context,
    category_audit_page_html,
)
from cs_tickets.portal_auth import portal_allow_confirm, tbc_auto_suggest_enabled
from cs_tickets.rule_compile import compile_llm_configured
from cs_tickets.portal_explain import explain_ticket_payload
from cs_tickets.portal_tbc_queue import (
    build_tbc_queue_payload,
    pending_tbc_rows,
    reclassify_run_rows,
    tbc_queue_page_html,
)
from cs_tickets.tbc_filter_nl import (
    build_filter_batch_rule_prefill,
    parse_review_focus_nl,
    review_focus_to_api_dict,
)
from cs_tickets.tbc_queue_filters import TbcQueueFilter, filter_pending_tbc_rows
from cs_tickets.portal_layout import portal_page_html
from cs_tickets.portal_stats import (
    category_index,
    classify_run_counts,
    classify_run_summary_html,
    tier_stats_table_html,
    tbc_reason_summary_html,
)
from cs_tickets.portal_ticket_preview import ticket_preview_html
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
from cs_tickets.run_metadata import build_run_metadata, build_workbook_filename
from cs_tickets.schema import MASTER_COLUMNS, TIER_COLUMNS

logger = logging.getLogger(__name__)

_STATIC_PROBE = "ticket_preview.js"


def _resolve_static_dir(module_file: str | Path) -> Path:
    """Locate portal static assets; fall back to repo src/ when package-data is incomplete."""
    pkg_static = Path(module_file).resolve().parent / "static"
    if (pkg_static / _STATIC_PROBE).is_file():
        return pkg_static
    candidates = [Path("/app/src/cs_tickets/static")]
    here = Path(module_file).resolve().parent
    for parent in here.parents:
        candidates.append(parent / "src" / "cs_tickets" / "static")
    for candidate in candidates:
        if (candidate / _STATIC_PROBE).is_file():
            logger.warning(
                "Installed package static dir missing %s; serving from %s",
                _STATIC_PROBE,
                candidate,
            )
            return candidate
    return pkg_static


_STATIC_DIR = _resolve_static_dir(__file__)
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
    tbc_reasons: dict[str, str]
    source_filename: str
    warns: int
    workbook_filename: str
    acked_tbc_ids: set[str] = field(default_factory=set)
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    bad_satisfaction_only: bool = False
    drive: DriveUploadResult | None = None
    drive_error: str | None = None
    last_audit_reclassify: dict[str, Any] | None = None


_RUNS: dict[str, _RunRecord] = {}


def _is_tbc_tier4(value: object) -> bool:
    return "tbc" in str(value or "").lower()


def _apply_run_overrides(record: _RunRecord) -> None:
    """Apply stored run-scoped overrides to record.rows in-place."""
    if not record.overrides:
        return
    for row in record.rows:
        tid = str(row.get("id") or "")
        ov = record.overrides.get(tid)
        if not ov:
            continue
        tier = ov.get("tier")
        if not isinstance(tier, (list, tuple)) or len(tier) != 5:
            continue
        for col, val in zip(TIER_COLUMNS, tier, strict=True):
            row[col] = val
        row["_manual_override"] = True
        row["_manual_override_note"] = str(ov.get("note") or "")
        record.tbc_reasons[tid] = "not_tbc" if not _is_tbc_tier4(tier[3]) else "other"


def _set_ticket_override(
    record: _RunRecord,
    *,
    ticket_id: str,
    tier: tuple[str, str, str, str, str],
    note: str = "",
) -> None:
    """Store run-scoped override and apply it to the current row snapshot."""
    record.overrides[str(ticket_id)] = {"tier": list(tier), "note": note.strip()}
    _apply_run_overrides(record)
    record.acked_tbc_ids.discard(str(ticket_id))


def _clear_ticket_override(record: _RunRecord, *, ticket_id: str) -> bool:
    """Remove run-scoped override. Returns True if an override existed."""
    existed = str(ticket_id) in record.overrides
    if existed:
        del record.overrides[str(ticket_id)]
    return existed


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
    preview_no_op_tuples: frozenset[tuple[str, str, str, str, str]] = frozenset()


_LEARN_UPLOADS: dict[str, _LearnRecord] = {}


def _drop_learn_upload(upload_id: str) -> None:
    record = _LEARN_UPLOADS.pop(upload_id, None)
    if record is not None and record.temp_dir.is_dir():
        shutil.rmtree(record.temp_dir, ignore_errors=True)


def _learn_error_html(message: str) -> str:
    body = f"""
    <h1 class="page-header">{REFERENCE_CATEGORIES_PAGE_TITLE}</h1>
    {learn_wizard_html(1)}
    <p class="meta drive-warning" role="alert">{_esc(message)}</p>
    <p class="links"><a href="/learn" class="btn">{LEARN_TRY_AGAIN_LABEL}</a></p>
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
    default_rules = frozenset(p.proposal_id for p in result.rule_proposals)
    default_tax = frozenset(p.proposal_id for p in result.taxonomy_proposals)
    current_rules = checked_rules if checked_rules is not None else default_rules
    current_tax = checked_tax if checked_tax is not None else default_tax
    preview_stale = (
        record.preview_selection_hash is not None
        and record.preview_selection_hash != learn_selection_hash(current_rules, current_tax)
    )
    preview_completed = record.preview_batch_result is not None
    wizard_step = 4 if preview_completed else 2
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
        preview_stale=preview_stale,
        bad_satisfaction_only=record.preview_bad_satisfaction_only,
        compute_no_op=record.preview_compute_no_op,
        preview_rule_ids=record.preview_rule_ids,
        preview_tax_ids=record.preview_tax_ids,
        no_op_tuples=record.preview_no_op_tuples,
    )
    session_details = learn_session_details_html(
        filename=result.filename,
        upload_id=upload_id,
        distinct_tier_paths=result.distinct_tier_paths,
        eligible_row_count=result.eligible_row_count,
    )
    page_body = f"""
    {learn_wizard_html(wizard_step, preview_completed=preview_completed)}
    <p class="run-summary" role="status">
        <span class="run-summary-lead">{result.row_count} rows parsed</span>
        <span class="run-summary-meta">({summary_meta})</span>
    </p>
    {session_details}
    {body}
    """
    return portal_page_html(
        title=REFERENCE_CATEGORIES_PAGE_TITLE,
        active="learn",
        body=page_body,
        extra_scripts=["/static/training.js?v=5", "/static/ticket_preview.js?v=9"],
    )


def _repo_root() -> Path:
    return resolve_repo_root()


def _sync_runtime_classifier(repo_root: Path | None = None) -> None:
    root = repo_root or _repo_root()
    ensure_live_bootstrapped(root)
    invalidate_runtime_cache()
    set_active_rule_specs(load_runtime_rule_specs(root))


def _default_allowlist():
    root = _repo_root()
    _sync_runtime_classifier(root)
    allow = load_runtime_allowlist(root)
    if len(allow.tuples) <= 5:
        logger.warning(
            "Allow-list is very small (%s tuples); runs/live/ may be empty or Drive sync failed. "
            "Local dev: ensure doc/ or references/ seeds exist, or set RUNTIME_CONFIG_DRIVE_ENABLED "
            "with GOOGLE_DRIVE_LIVE_FOLDER_ID for deployed config.",
            len(allow.tuples),
        )
    return allow


def _default_taxonomy_path() -> Path | None:
    tax = _repo_root() / "doc" / "Taxonomy.csv"
    return tax if tax.is_file() else None


def _classify_technical_details_html() -> str:
    return f"""
    <details class="technical-details">
        <summary>{TECHNICAL_DETAILS_SUMMARY}</summary>
        <div class="technical-details-body meta">{TECHNICAL_DETAILS_BODY}</div>
    </details>"""


def _classify_run_actions_html(
    run_id: str,
    *,
    primary: bool = False,
    tbc_pending: int = 0,
) -> str:
    primary_cls = " btn-primary" if primary else " btn-secondary"
    tbc_btn = ""
    if tbc_pending > 0:
        tbc_btn = (
            f'<a href="/run/{_esc(run_id)}/tbc" class="btn btn-primary">'
            f"{TBC_QUEUE_BUTTON} ({tbc_pending})</a> "
        )
    return f"""
    <p class="run-actions">
        {tbc_btn}
        <a href="/run/{_esc(run_id)}/category_audit" class="btn btn-secondary">{CATEGORY_AUDIT_BUTTON}</a>
        <a href="/download/{_esc(run_id)}" class="btn{primary_cls}">{DOWNLOAD_WORKBOOK_LABEL}</a>
        <a href="/" class="btn btn-secondary">{NEW_UPLOAD_LABEL}</a>
        <a href="{_esc(drive_runs_folder_url())}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary">{NAV_RUN_HISTORY}</a>
    </p>"""


def _run_results_body_html(
    run_id: str,
    record: _RunRecord,
    *,
    status_banner: str = "",
) -> str:
    counts = classify_run_counts(record.rows)
    pending = len(pending_tbc_rows(record.rows, acked_ids=record.acked_tbc_ids))
    summary_block = classify_run_summary_html(record.rows, warns=record.warns)
    reason_block = tbc_reason_summary_html(record.tbc_reasons, headline_tbc=counts.tbc)
    stats_block = tier_stats_table_html(record.rows, run_id=run_id)
    preview_block = ticket_preview_html(
        record.rows,
        tbc_reasons=record.tbc_reasons,
        categories=category_index(record.rows),
        run_id=run_id,
    )
    drive_html = _drive_result_html(record.drive, record.drive_error)
    filter_note = ""
    if record.bad_satisfaction_only:
        filter_note = '<p class="meta run-filter-note">This run included only tickets with a bad CSAT rating.</p>'
    run_actions = _classify_run_actions_html(
        run_id,
        primary=True,
        tbc_pending=pending,
    )
    return f"""
    {status_banner}
    {summary_block}
    {reason_block}
    {filter_note}
    {run_actions}
    {drive_html}
    <p class="download-hint meta">Workbook includes sheets <strong>Run metadata</strong>, <strong>Tickets</strong> (full rows), and <strong>Tier breakdown</strong> (category counts).</p>

    <h2 class="section-header">{CATEGORY_BREAKDOWN_HEADING}</h2>
    <p class="meta">{CATEGORY_BREAKDOWN_META}</p>
    <div class="stats-wrap">{stats_block}</div>

    <h2 class="section-header">{TICKET_PREVIEW_HEADING}</h2>
    <div id="ticket-preview">{preview_block}</div>

    {_classify_technical_details_html()}
    """


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
        tbc_reasons: dict[str, str] = {}
        warns = 0
        try:
            for row, warn, reason in iter_master_rows_with_meta(
                tmp_path,
                allow,
                bad_satisfaction_only=bad_satisfaction_only,
            ):
                if warn:
                    warns += 1
                ticket_id = str(row.get("id") or "")
                tbc_reasons[ticket_id] = reason
                # Keep a few non-workbook fields for portal-only workflows (audit sweeps, UX hints).
                kept = {k: row.get(k) for k in MASTER_COLUMNS}
                requester_email = row.get("requester_email")
                if requester_email:
                    kept["requester_email"] = requester_email
                rows.append(kept)
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
            tbc_reasons=tbc_reasons,
            source_filename=source_filename,
            warns=warns,
            workbook_filename=workbook_filename,
            bad_satisfaction_only=bad_satisfaction_only,
            drive=drive_result,
            drive_error=drive_error,
        )
        record = _RUNS[run_id]
        trends_html = ""
        if trends_snapshot is not None:
            snap_rows, snap_tbc = trends_snapshot
            snap_pct = f"{100.0 * snap_tbc / snap_rows:.1f}%" if snap_rows else "0.0%"
            trends_html = (
                f'<p class="meta trends-snapshot-ok">'
                f"Added to <a href=\"/dashboard\">{NAV_TBC_TRENDS}</a>: "
                f"{snap_rows} tickets ({snap_tbc} manual review, {snap_pct}).</p>"
            )
        body = trends_html + _run_results_body_html(run_id, record)
        return portal_page_html(
            title="Categorization results",
            active="categorize",
            body=body,
            extra_scripts=["/static/ticket_preview.js?v=9"],
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _esc(v: object) -> str:
    if v is None:
        return ""
    # Must be safe for HTML attributes and text nodes.
    s = html.escape(str(v), quote=True)
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


def _get_run_record(run_id: str) -> _RunRecord:
    record = _RUNS.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Unknown or expired run_id")
    return record


@app.get("/run/{run_id}/results", response_class=HTMLResponse)
def run_results(run_id: str, reclassified: str | None = None) -> str:
    record = _get_run_record(run_id)
    banner = ""
    if reclassified:
        counts = classify_run_counts(record.rows)
        banner = (
            f'<p class="run-summary" role="status" id="tbc-reclassify-banner">'
            f"Run re-classified with current live rules. "
            f"{counts.tbc} ticket{'s' if counts.tbc != 1 else ''} need manual review.</p>"
        )
    body = _run_results_body_html(run_id, record, status_banner=banner)
    return portal_page_html(
        title="Categorization results",
        active="categorize",
        body=body,
        extra_scripts=["/static/ticket_preview.js?v=9"],
    )


@app.get("/run/{run_id}/category_audit", response_class=HTMLResponse)
def run_category_audit_page(
    run_id: str,
    q: str | None = None,
    tier1: str | None = None,
    categories: str | None = None,
    tier4: str | None = None,
    include_tbc: str | None = None,
    offset: int = 0,
    limit: int = DEFAULT_CHUNK_SIZE,
    reclassified: str | None = None,
) -> str:
    record = _get_run_record(run_id)
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="limit must be 1–50")
    audit_filter = CategoryAuditFilter.from_query(
        q=q,
        tier1=tier1,
        categories=categories,
        tier4=tier4,
        include_tbc=include_tbc,
    )
    slice_rows, stats = build_category_audit_context(record.rows, audit_filter)
    chunk_rows = slice_rows[offset : offset + limit]
    reclassify_banner = _audit_reclassify_banner_html(
        record,
        audit_filter,
        show=bool(reclassified),
    )
    body = category_audit_page_html(
        run_id=run_id,
        slice_rows=slice_rows,
        chunk_rows=chunk_rows,
        filt=audit_filter,
        stats=stats,
        offset=offset,
        limit=limit,
        reclassify_banner=reclassify_banner,
    )
    return portal_page_html(
        title="Category audit",
        active="categorize",
        body=body,
        extra_scripts=["/static/category_audit.js?v=4"],
    )


def _audit_reclassify_banner_html(
    record: _RunRecord,
    filt: CategoryAuditFilter,
    *,
    show: bool,
) -> str:
    if not show or not record.last_audit_reclassify:
        return ""
    snap = record.last_audit_reclassify
    if snap.get("filter") != filt.as_dict():
        return ""
    from cs_tickets.portal_copy import CATEGORY_AUDIT_RECLASSIFY_BANNER

    text = CATEGORY_AUDIT_RECLASSIFY_BANNER.format(
        slice_label=snap.get("slice_label") or filt.slice_label(),
        slice_before=snap.get("slice_count_before", "?"),
        slice_after=snap.get("slice_count_after", "?"),
        tbc_before=snap.get("tbc_before", "?"),
        tbc_after=snap.get("tbc_after", "?"),
    )
    return f'<p class="run-summary" role="status" id="category-audit-reclassify-banner">{text}</p>'


def _audit_filter_from_body(body: dict) -> CategoryAuditFilter:
    cats = body.get("categories")
    if isinstance(cats, list):
        categories = ",".join(str(c) for c in cats)
    else:
        categories = str(cats or "") if cats else None
    return CategoryAuditFilter.from_query(
        q=str(body.get("q") or "") or None,
        tier1=str(body.get("tier1") or "") or None,
        categories=categories,
        tier4=str(body.get("tier4") or "") or None,
        include_tbc=body.get("include_tbc"),
    )


@app.get("/run/{run_id}/category_audit/sweeps")
def run_category_audit_sweeps_json(
    run_id: str,
    q: str | None = None,
    tier1: str | None = None,
    categories: str | None = None,
    tier4: str | None = None,
    include_tbc: str | None = None,
) -> JSONResponse:
    record = _get_run_record(run_id)
    audit_filter = CategoryAuditFilter.from_query(
        q=q,
        tier1=tier1,
        categories=categories,
        tier4=tier4,
        include_tbc=include_tbc,
    )
    slice_rows, stats = build_category_audit_context(record.rows, audit_filter)
    allow = _default_allowlist()
    sweeps = run_category_audit_sweeps(slice_rows, allow)
    return JSONResponse(
        {
            "run_id": run_id,
            "filter": audit_filter.as_dict(),
            "stats": stats,
            "sweeps": [s.as_dict() for s in sweeps],
        }
    )


@app.get("/run/{run_id}/category_audit/export.csv")
def run_category_audit_export_csv(
    run_id: str,
    q: str | None = None,
    tier1: str | None = None,
    categories: str | None = None,
    tier4: str | None = None,
    include_tbc: str | None = None,
) -> Response:
    record = _get_run_record(run_id)
    audit_filter = CategoryAuditFilter.from_query(
        q=q,
        tier1=tier1,
        categories=categories,
        tier4=tier4,
        include_tbc=include_tbc,
    )
    slice_rows, _stats = build_category_audit_context(record.rows, audit_filter)
    payload = category_audit_slice_csv_bytes(slice_rows)
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="category_audit_export.csv"',
        },
    )


@app.post("/run/{run_id}/category_audit_parse_focus")
def run_category_audit_parse_focus(run_id: str, body: dict = Body(...)) -> JSONResponse:
    _get_run_record(run_id)
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    allow = _default_allowlist()
    result = parse_review_focus_nl(text, allow, use_llm=compile_llm_configured())
    payload = review_focus_to_api_dict(result)
    tbf = result.filter
    audit_filter = CategoryAuditFilter.from_query(
        q=tbf.q or None,
        tier1=tbf.tier1 or None,
        categories=",".join(tbf.categories) if tbf.categories else None,
        include_tbc=body.get("include_tbc"),
    )
    payload["audit_filter"] = audit_filter.as_dict()
    payload["audit_url"] = (
        f"/run/{run_id}/category_audit?{audit_filter.to_query_string()}"
        if audit_filter.to_query_string()
        else f"/run/{run_id}/category_audit"
    )
    return JSONResponse(payload)


@app.post("/run/{run_id}/run_parse_focus")
def run_parse_focus(run_id: str, body: dict = Body(...)) -> JSONResponse:
    """Parse natural-language focus for filtering the full run preview (not only TBC)."""
    _get_run_record(run_id)
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    allow = _default_allowlist()
    result = parse_review_focus_nl(text, allow, use_llm=compile_llm_configured())
    payload = review_focus_to_api_dict(result)
    # Provide the parsed fields directly for the run preview UI.
    payload["run_filter"] = {
        "q": result.filter.q,
        "tier1": result.filter.tier1,
        "categories": list(result.filter.categories),
    }
    return JSONResponse(payload)


@app.post("/rules/parse_focus")
def rules_parse_focus(body: dict = Body(...)) -> JSONResponse:
    """Parse natural-language focus for filtering the /rules list page."""
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    allow = _default_allowlist()
    result = parse_review_focus_nl(text, allow, use_llm=compile_llm_configured())
    payload = review_focus_to_api_dict(result)

    # Map queue-style focus fields onto /rules filters.
    # /rules supports q (substring search across id, matchers, and tier path) and tier1.
    q_parts: list[str] = []
    filt = result.filter
    if getattr(filt, "q", ""):
        q_parts.append(str(getattr(filt, "q") or "").strip())
    cats = list(getattr(filt, "categories", ()) or ())
    q_parts.extend([str(c).strip() for c in cats if str(c).strip()])
    rules_q = " ".join([p for p in q_parts if p]).strip()
    rules_tier1 = str(getattr(filt, "tier1", "") or "").strip()

    payload["rule_filter"] = {
        "q": rules_q,
        "tier1": rules_tier1,
    }
    from urllib.parse import urlencode

    qs = urlencode({k: v for k, v in payload["rule_filter"].items() if v})
    payload["rules_url"] = f"/rules?{qs}" if qs else "/rules"
    return JSONResponse(payload)


@app.get("/run/{run_id}/ticket/{ticket_id}")
def run_ticket_json(run_id: str, ticket_id: str) -> JSONResponse:
    """Lightweight ticket detail for inline preview UIs (rule preview, audit panels)."""
    record = _get_run_record(run_id)
    row = next((r for r in record.rows if str(r.get("id") or "") == str(ticket_id)), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Ticket not found in this run")
    tier = [row.get(c) or "" for c in TIER_COLUMNS]
    return JSONResponse(
        {
            "ok": True,
            "ticket": {
                "id": str(row.get("id") or ""),
                "subject": str(row.get("subject") or ""),
                "description": str(row.get("description") or ""),
                "tags": row.get("tags") or "",
                "requester_email": str(row.get("requester_email") or ""),
                "tier": tier,
            },
        }
    )

@app.get("/run/{run_id}/tbc", response_class=HTMLResponse)
def run_tbc_queue_page(run_id: str, reclassified: str | None = None) -> str:
    record = _get_run_record(run_id)
    counts = classify_run_counts(record.rows)
    pending = len(pending_tbc_rows(record.rows, acked_ids=record.acked_tbc_ids))
    banner = ""
    if reclassified:
        banner = (
            '<p class="run-summary" role="status" id="tbc-reclassify-banner" hidden></p>'
        )
    body = tbc_queue_page_html(
        run_id=run_id,
        total_pending=pending,
        total_tbc=counts.tbc,
        reclassify_banner=banner,
        auto_suggest=tbc_auto_suggest_enabled(),
        llm_available=compile_llm_configured(),
        can_confirm=portal_allow_confirm(),
        can_add_allowlist=portal_allow_confirm() and training_available(_repo_root()),
    )
    return portal_page_html(
        title=TBC_QUEUE_PAGE_TITLE,
        active="categorize",
        body=body,
        extra_scripts=["/static/tbc_queue.js?v=9"],
    )


@app.post("/run/{run_id}/suggest_category/{ticket_id}")
def run_suggest_category(run_id: str, ticket_id: str) -> JSONResponse:
    record = _get_run_record(run_id)
    row = next((r for r in record.rows if str(r.get("id") or "") == ticket_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Ticket not found in this run")
    repo_root = _repo_root()
    allow = _default_allowlist()
    rule_specs = load_runtime_rule_specs(repo_root)
    explain = explain_ticket_payload(row, allow, rule_specs=rule_specs)
    result = suggest_category_for_ticket(
        row,
        allow,
        explain_payload=explain,
        live_rules=rule_specs,
        use_llm=compile_llm_configured(),
        taxonomy_csv=_default_taxonomy_path(),
    )
    return JSONResponse(suggest_result_to_api_dict(result))


@app.post("/run/{run_id}/add_allowlist_tuple/{ticket_id}")
def run_add_allowlist_tuple(run_id: str, ticket_id: str, body: dict = Body(...)) -> JSONResponse:
    if not portal_allow_confirm():
        raise HTTPException(status_code=403, detail="Team lead confirmation required.")
    repo_root = _repo_root()
    if not training_available(repo_root):
        raise HTTPException(status_code=503, detail="Reference workbook is not writable.")

    tier_raw = body.get("tier")
    if not isinstance(tier_raw, list) or len(tier_raw) != 5:
        raise HTTPException(status_code=400, detail="tier must be a 5-element list.")

    record = _get_run_record(run_id)
    row = next((r for r in record.rows if str(r.get("id") or "") == ticket_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Ticket not found in this run")

    tier = tuple(str(x) for x in tier_raw)
    try:
        result = commit_tbc_exemplar(repo_root, tier, row)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    invalidate_runtime_cache()
    return JSONResponse(
        {
            "ok": True,
            "message": commit_success_message(result),
            "rows_added": result.rows_added,
            "rules_added": result.rules_added,
            "rules_skipped": result.rules_skipped,
            "tier": list(tier),
        }
    )


@app.get("/run/{run_id}/tbc_queue")
def run_tbc_queue_json(
    run_id: str,
    offset: int = 0,
    limit: int = 10,
    q: str | None = None,
    tier1: str | None = None,
    categories: str | None = None,
    tbc_reason: str | None = None,
    include_facets: int = 0,
) -> JSONResponse:
    record = _get_run_record(run_id)
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="limit must be 1–50")
    repo_root = _repo_root()
    allow = _default_allowlist()
    rule_specs = load_runtime_rule_specs(repo_root)
    queue_filter = TbcQueueFilter.from_query(
        q=q,
        tier1=tier1,
        categories=categories,
        tbc_reason=tbc_reason,
    )
    payload = build_tbc_queue_payload(
        run_id=run_id,
        rows=record.rows,
        tbc_reasons=record.tbc_reasons,
        acked_ids=record.acked_tbc_ids,
        allow=allow,
        rule_specs=rule_specs,
        offset=offset,
        limit=limit,
        queue_filter=queue_filter,
        include_facets=bool(include_facets),
    )
    return JSONResponse(payload)


def _filtered_pending_for_run(
    record,
    allow,
    rule_specs,
    queue_filter: TbcQueueFilter,
) -> list[tuple[dict, dict]]:
    all_pending = pending_tbc_rows(record.rows, acked_ids=record.acked_tbc_ids)
    return filter_pending_tbc_rows(
        all_pending,
        allow,
        rule_specs,
        queue_filter,
        tbc_reasons=record.tbc_reasons,
    )


@app.post("/run/{run_id}/tbc_parse_focus")
def run_tbc_parse_focus(run_id: str, body: dict = Body(...)) -> JSONResponse:
    _get_run_record(run_id)
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    allow = _default_allowlist()
    result = parse_review_focus_nl(text, allow, use_llm=compile_llm_configured())
    return JSONResponse(review_focus_to_api_dict(result))


@app.post("/run/{run_id}/tbc_draft_rule_for_filter")
def run_tbc_draft_rule_for_filter(run_id: str, body: dict = Body(...)) -> JSONResponse:
    record = _get_run_record(run_id)
    repo_root = _repo_root()
    allow = _default_allowlist()
    rule_specs = load_runtime_rule_specs(repo_root)
    queue_filter = TbcQueueFilter.from_query(
        q=str(body.get("q") or ""),
        tier1=str(body.get("tier1") or ""),
        categories=str(body.get("categories") or ""),
        tbc_reason=str(body.get("tbc_reason") or ""),
    )
    if not queue_filter.active:
        raise HTTPException(status_code=400, detail="Set a review focus before drafting a batch rule.")
    matched = _filtered_pending_for_run(record, allow, rule_specs, queue_filter)
    sample_ids: list[str] = []
    sample_quotes: list[str] = []
    for row, _explain in matched[:3]:
        sample_ids.append(str(row.get("id") or ""))
        sample_quotes.append(quote_snippet(row))
    rule_target = str(body.get("rule_target") or "").strip()
    prefill = build_filter_batch_rule_prefill(
        queue_filter,
        matched_count=len(matched),
        sample_ticket_ids=tuple(sample_ids),
        sample_quotes=tuple(sample_quotes),
        rule_target=rule_target,
    )
    return JSONResponse(
        {
            "ok": True,
            "prefill": prefill,
            "matched_count": len(matched),
            "filter": queue_filter.as_dict(),
            "rule_target": rule_target,
        }
    )


@app.post("/run/{run_id}/tbc_chunk/ack")
def run_tbc_chunk_ack(run_id: str, body: dict = Body(...)) -> JSONResponse:
    record = _get_run_record(run_id)
    raw_ids = body.get("ticket_ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="ticket_ids must be a list")
    for tid in raw_ids:
        record.acked_tbc_ids.add(str(tid))
    limit = int(body.get("limit") or 10)
    limit = max(1, min(limit, 50))
    offset = int(body.get("offset") or 0)
    repo_root = _repo_root()
    allow = _default_allowlist()
    rule_specs = load_runtime_rule_specs(repo_root)
    queue_filter = TbcQueueFilter.from_query(
        q=str(body.get("q") or ""),
        tier1=str(body.get("tier1") or ""),
        categories=str(body.get("categories") or ""),
        tbc_reason=str(body.get("tbc_reason") or ""),
    )
    all_pending = pending_tbc_rows(record.rows, acked_ids=record.acked_tbc_ids)
    total_pending_unfiltered = len(all_pending)
    if queue_filter.active:
        filtered = _filtered_pending_for_run(record, allow, rule_specs, queue_filter)
        pending_count = len(filtered)
    else:
        pending_count = total_pending_unfiltered
    queue_complete = total_pending_unfiltered == 0
    next_offset = min(offset, max(0, pending_count - limit)) if pending_count else 0
    if limit > 0 and next_offset > 0:
        next_offset = (next_offset // limit) * limit
    return JSONResponse(
        {
            "ok": True,
            "acked": len(raw_ids),
            "total_pending": pending_count,
            "total_pending_unfiltered": total_pending_unfiltered,
            "queue_complete": queue_complete,
            "has_next": next_offset < pending_count,
            "next_offset": next_offset,
            "filter": queue_filter.as_dict(),
        }
    )


@app.post("/run/{run_id}/reclassify")
def run_reclassify(run_id: str, body: dict | None = Body(None)) -> JSONResponse:
    record = _get_run_record(run_id)
    repo_root = _repo_root()
    allow = _default_allowlist()
    rule_specs = load_runtime_rule_specs(repo_root)
    tbc_before = classify_run_counts(record.rows).tbc

    audit_filter: CategoryAuditFilter | None = None
    slice_before: int | None = None
    if body and body.get("snapshot_audit"):
        audit_filter = _audit_filter_from_body(body)
        slice_before = len(build_category_audit_context(record.rows, audit_filter)[0])

    rows, tbc_reasons, warns = reclassify_run_rows(
        record.rows,
        allow,
        rule_specs,
    )
    record.rows = rows
    record.tbc_reasons = tbc_reasons
    record.warns = warns
    record.acked_tbc_ids.clear()
    _apply_run_overrides(record)
    tbc_after = classify_run_counts(record.rows).tbc

    if audit_filter is not None and slice_before is not None:
        slice_after = len(build_category_audit_context(record.rows, audit_filter)[0])
        record.last_audit_reclassify = {
            "filter": audit_filter.as_dict(),
            "slice_label": audit_filter.slice_label(),
            "slice_count_before": slice_before,
            "slice_count_after": slice_after,
            "tbc_before": tbc_before,
            "tbc_after": tbc_after,
        }

    payload: dict[str, Any] = {
        "ok": True,
        "tbc_before": tbc_before,
        "tbc_after": tbc_after,
        "total": len(record.rows),
    }
    if record.last_audit_reclassify:
        payload["audit_reclassify"] = record.last_audit_reclassify
    return JSONResponse(payload)


@app.post("/run/{run_id}/override/{ticket_id}")
def run_ticket_override(run_id: str, ticket_id: str, body: dict = Body(...)) -> JSONResponse:
    """Run-scoped single-ticket classification override (does not change live rules)."""
    record = _get_run_record(run_id)
    allow = _default_allowlist()
    tier_raw = body.get("tier")
    if not isinstance(tier_raw, list) or len(tier_raw) != 5:
        raise HTTPException(status_code=400, detail="tier must be a 5-element list.")
    tier = tuple(str(x) for x in tier_raw)
    if tier not in allow.tuples:
        raise HTTPException(status_code=400, detail="tier is not in allow-list.")
    if _is_tbc_tier4(tier[3]):
        raise HTTPException(status_code=400, detail="Override tier cannot be a TBC/manual-review category.")
    row = next((r for r in record.rows if str(r.get("id") or "") == str(ticket_id)), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Ticket not found in this run")
    note = str(body.get("note") or "").strip()
    _set_ticket_override(record, ticket_id=str(ticket_id), tier=tier, note=note)
    return JSONResponse({"ok": True, "ticket_id": str(ticket_id), "tier": list(tier)})


@app.post("/run/{run_id}/override/{ticket_id}/clear")
def run_ticket_override_clear(run_id: str, ticket_id: str) -> JSONResponse:
    """Clear run-scoped single-ticket override and require a re-classify to recompute tiers."""
    record = _get_run_record(run_id)
    existed = _clear_ticket_override(record, ticket_id=str(ticket_id))
    return JSONResponse({"ok": True, "cleared": existed, "ticket_id": str(ticket_id)})


@app.get("/run/{run_id}/explain/{ticket_id}", response_model=None)
def explain_ticket(
    run_id: str,
    ticket_id: str,
    format: str | None = None,
) -> Response:
    record = _RUNS.get(run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Unknown or expired run_id")
    row = next((r for r in record.rows if str(r.get("id") or "") == ticket_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Ticket not found in this run")
    repo_root = _repo_root()
    allow = _default_allowlist()
    rule_specs = load_runtime_rule_specs(repo_root)
    payload = explain_ticket_payload(row, allow, rule_specs=rule_specs)
    if format == "json":
        return JSONResponse(payload)
    tier_path = " → ".join(payload["tier"])
    rules = "".join(
        f"<li><code>{_esc(ev['rule_id'])}</code> "
        f"(weight {ev['weight']}, {_esc(ev['signal'])})</li>"
        for ev in payload["evidence"]
    )
    html = f"""
<div class="classification-explain">
  <p><strong>Category:</strong> {_esc(tier_path)}</p>
  <p><strong>Score:</strong> {payload['score']}</p>
  <ul>{rules or '<li>No rules fired</li>'}</ul>
</div>""".strip()
    return HTMLResponse(html)


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
                <button type="submit" class="btn btn-primary">{LEARN_PROCESS_BUTTON}</button>
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
    except Exception as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        logger.exception("Learn process failed for %s", source_filename)
        return _learn_error_html(f"Could not process workbook: {exc}")

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
        no_op = getattr(batch_result, "selection_no_op_tuples", None)
        record.preview_no_op_tuples = no_op if no_op is not None else frozenset()
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
    <p class="links"><a href="/learn" class="btn">{LEARN_UPLOAD_ANOTHER_LABEL}</a></p>
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

    drive_sync, drive_error, drive_skip = try_sync_live_to_drive(
        live,
        proposals_dir=confirm_result.proposals_dir,
        backup_version=confirm_result.config_version_before,
    )
    _sync_runtime_classifier(repo_root)
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
        <a href="/learn" class="btn">{LEARN_UPLOAD_ANOTHER_LABEL}</a>
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
    try_sync_live_to_drive(live, backup_version=restored_version)
    _sync_runtime_classifier(repo_root)
    revert_footer = learn_revert_footer_html(show_revert=has_revertable_live_backup(live))
    body = f"""
    <h1 class="page-header">{REFERENCE_CATEGORIES_PAGE_TITLE}</h1>
    <p class="run-summary" role="status">Restored live config to version {restored_version}.</p>
    <p class="meta">The next categorisation run will use the reverted allow-list and rules.</p>
    <p class="links"><a href="/learn" class="btn">{LEARN_UPLOAD_ANOTHER_LABEL}</a></p>
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


def _rules_run_row(run_id: str, ticket_id: str) -> dict | None:
    record = _RUNS.get(run_id)
    if not record:
        return None
    return next((r for r in record.rows if str(r.get("id") or "") == ticket_id), None)


@app.get("/rules", response_class=HTMLResponse)
def rules_index(
    confirmed: str | None = None,
    version: str | None = None,
    q: str | None = None,
    tier1: str | None = None,
    tier2: str | None = None,
    tier3: str | None = None,
    tier4: str | None = None,
    status: str | None = None,
    override: str | None = None,
) -> str:
    repo_root = _repo_root()
    ensure_live_bootstrapped(repo_root)
    rules = load_runtime_rule_specs(repo_root, include_disabled=True)
    from cs_tickets.portal_rules import filter_rules, rules_filter_bar_html

    filtered = filter_rules(
        rules,
        q=str(q or ""),
        tier1=str(tier1 or ""),
        tier2=str(tier2 or ""),
        tier3=str(tier3 or ""),
        tier4=str(tier4 or ""),
        status=str(status or ""),
        override=str(override or ""),
    )
    banner = ""
    if confirmed:
        ver = version or str(current_config_version(repo_root))
        banner = f'<p class="run-summary" role="status">Rule confirmed. Live config version {_esc(ver)}.</p>'
    can_confirm = portal_allow_confirm()
    filter_bar = rules_filter_bar_html(
        q=str(q or ""),
        tier1=str(tier1 or ""),
        tier2=str(tier2 or ""),
        tier3=str(tier3 or ""),
        tier4=str(tier4 or ""),
        status=str(status or ""),
        override=str(override or ""),
        total=len(rules),
        shown=len(filtered),
    )
    body = f"""
    <h1 class="page-header">{RULES_PAGE_TITLE}</h1>
    <p class="meta">{RULES_PAGE_INTRO}</p>
    {banner}
    <p class="links"><a href="/rules/new" class="btn btn-primary">{RULES_NEW_BUTTON}</a></p>
    {filter_bar}
    {rules_list_html(filtered, config_version=current_config_version(repo_root), can_confirm=can_confirm)}
    """
    return portal_page_html(
        title=RULES_PAGE_TITLE,
        active="rules",
        body=body,
        extra_scripts=["/static/rules.js?v=9", "/static/training.js?v=5"],
    )


@app.get("/rules/new", response_class=HTMLResponse)
def rules_new(
    run_id: str | None = None,
    ticket_id: str | None = None,
    rule_id: str | None = None,
) -> str:
    prefill = ""
    initial_rule = None
    repo_root = _repo_root()
    if rule_id:
        for rule in load_runtime_rule_specs(repo_root, include_disabled=True):
            if rule.id == rule_id:
                initial_rule = rule
                break
    if run_id and ticket_id:
        row = _rules_run_row(run_id, ticket_id)
        if row:
            allow = _default_allowlist()
            rule_specs = load_runtime_rule_specs(repo_root)
            explain = explain_ticket_payload(row, allow, rule_specs=rule_specs)
            top_ev = ""
            if explain.get("evidence"):
                top_ev = str(explain["evidence"][0].get("rule_id") or "")
            tier_hint = " → ".join(explain.get("tier") or [])[:80]
            prefill = build_rule_prefill(
                ticket_id=ticket_id,
                subject=str(row.get("subject") or ""),
                suggested_tier=tier_hint,
                why_tbc=str(explain.get("tbc_reason_detail") or explain.get("tbc_reason") or ""),
                explain_evidence=top_ev,
                row=row,
                explain=explain,
            )
    can_confirm = portal_allow_confirm()
    body = f"""
    <h1 class="page-header">{RULES_PAGE_TITLE}</h1>
    <p class="links"><a href="/rules" class="btn btn-secondary">← All rules</a></p>
    {rules_editor_html(
        prefill=prefill,
        run_id=run_id or "",
        ticket_id=ticket_id or "",
        initial_rule=initial_rule,
        can_confirm=can_confirm,
    )}
    """
    return portal_page_html(
        title=RULES_PAGE_TITLE,
        active="rules",
        body=body,
        extra_scripts=["/static/rules.js?v=9"],
    )


@app.post("/rules/compile")
def rules_compile(body: dict = Body(...)) -> JSONResponse:
    messages = body.get("messages") or []
    if not messages:
        raise HTTPException(status_code=400, detail="messages required")
    last_user = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_user = str(msg.get("content") or "")
            break
    if not last_user:
        raise HTTPException(status_code=400, detail="No user message")

    repo_root = _repo_root()
    allow = load_runtime_allowlist(repo_root)
    live_rules = load_runtime_rule_specs(repo_root)

    prior_rule = None
    prior_raw = body.get("prior_rule")
    if isinstance(prior_raw, dict) and prior_raw.get("id"):
        try:
            prior_rule = parse_rule_json(prior_raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    exemplar_row = None
    explain_payload = None
    run_id = str(body.get("run_id") or "")
    ticket_id = str(body.get("exemplar_ticket_id") or "")
    if run_id and ticket_id:
        exemplar_row = _rules_run_row(run_id, ticket_id)
        if exemplar_row:
            explain_payload = explain_ticket_payload(
                exemplar_row,
                allow,
                rule_specs=live_rules,
            )

    result = compile_rule_message(
        last_user,
        allow=allow,
        live_rules=live_rules,
        prior_rule=prior_rule,
        exemplar_row=exemplar_row,
        explain_payload=explain_payload,
    )
    return JSONResponse(compile_result_to_api_dict(result))


@app.post("/rules/confirm")
def rules_confirm(body: dict = Body(...)) -> JSONResponse:
    if not portal_allow_confirm():
        raise HTTPException(
            status_code=403,
            detail="Confirm requires team lead access (set PORTAL_ALLOW_CONFIRM=1).",
        )
    raw = body.get("rule")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="rule object required")
    try:
        rule = parse_rule_json(raw)
    except ValueError as exc:
        return JSONResponse({"ok": False, "errors": [str(exc)]})
    repo_root = _repo_root()
    live = ensure_live_bootstrapped(repo_root)
    try:
        result = confirm_explicit_rule(live, rule)
    except PromoteError as exc:
        return JSONResponse({"ok": False, "errors": [str(exc)]})
    try_sync_live_to_drive(live, proposals_dir=result.proposals_dir)
    _sync_runtime_classifier(repo_root)
    return JSONResponse(
        {
            "ok": True,
            "config_version_after": result.config_version_after,
            "rule_id": rule.id,
        }
    )


@app.post("/rules/confirm_batch")
def rules_confirm_batch(body: dict = Body(...)) -> JSONResponse:
    if not portal_allow_confirm():
        raise HTTPException(
            status_code=403,
            detail="Confirm requires team lead access (set PORTAL_ALLOW_CONFIRM=1).",
        )
    raw_rules = body.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise HTTPException(status_code=400, detail="rules must be a non-empty list")
    rules: list = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="each rule must be an object")
        try:
            rules.append(parse_rule_json(raw))
        except ValueError as exc:
            return JSONResponse({"ok": False, "errors": [str(exc)]})
    repo_root = _repo_root()
    live = ensure_live_bootstrapped(repo_root)
    try:
        result = confirm_explicit_rules_batch(live, tuple(rules))
    except PromoteError as exc:
        return JSONResponse({"ok": False, "errors": [str(exc)]})
    try_sync_live_to_drive(live, proposals_dir=result.proposals_dir)
    _sync_runtime_classifier(repo_root)
    return JSONResponse(
        {
            "ok": True,
            "config_version_after": result.config_version_after,
            "rule_ids": list(result.accepted_rule_ids),
            "rules_added": result.rules_added,
        }
    )


@app.post("/rules/preview")
def rules_preview(body: dict = Body(...)) -> JSONResponse:
    raw = body.get("rule")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="rule required")
    try:
        candidate = parse_rule_json(raw)
    except ValueError as exc:
        return JSONResponse({"ok": False, "errors": [str(exc)]})
    run_id = str(body.get("run_id") or "")
    ticket_ids = tuple(str(t) for t in (body.get("ticket_ids") or []) if t)
    rows: list[dict] = []
    if run_id and run_id in _RUNS:
        rows = _RUNS[run_id].rows
    repo_root = _repo_root()
    allow = load_runtime_allowlist(repo_root)
    live_rules = load_runtime_rule_specs(repo_root)
    results = preview_rule_on_rows(
        rows,
        allow,
        live_rules,
        candidate,
        ticket_ids=ticket_ids,
    )
    return JSONResponse({"ok": True, "results": results})


@app.post("/rules/preview_upload")
async def rules_preview_upload(
    export: UploadFile = File(...),
    rule: str = Form(...),
    limit: str | None = Form(None),
) -> JSONResponse:
    """Preview a candidate rule against an uploaded export file (sandbox, no run_id required)."""
    _require_extension(export.filename, _JSON_EXTENSIONS, "Export file")
    raw_limit = int(limit or 200)
    raw_limit = max(1, min(raw_limit, 2000))

    try:
        rule_obj = json.loads(rule)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"rule must be JSON: {exc}") from exc
    if not isinstance(rule_obj, dict):
        raise HTTPException(status_code=400, detail="rule JSON must be an object")

    try:
        candidate = parse_rule_json(rule_obj)
    except ValueError as exc:
        return JSONResponse({"ok": False, "errors": [str(exc)]})

    repo_root = _repo_root()
    allow = load_runtime_allowlist(repo_root)
    live_rules = load_runtime_rule_specs(repo_root)

    suffix = Path(export.filename or "export.json").suffix or ".json"
    tmpdir = tempfile.mkdtemp(prefix="cs_rules_preview_")
    tmp_path = Path(tmpdir) / f"export{suffix}"
    try:
        tmp_path.write_bytes(await export.read())

        rows: list[dict[str, Any]] = []
        warns = 0
        for row, warn in iter_master_rows(tmp_path, allow, limit=raw_limit):
            if warn:
                warns += 1
            kept: dict[str, Any] = {k: row.get(k) for k in MASTER_COLUMNS}
            requester_email = row.get("requester_email")
            if requester_email:
                kept["requester_email"] = requester_email
            rows.append(kept)

        results = preview_rule_on_rows(
            rows,
            allow,
            live_rules,
            candidate,
            ticket_ids=(),
            limit=200,  # UI preview should stay small
        )
        by_id: dict[str, dict[str, Any]] = {str(r.get("id") or ""): r for r in rows}
        for item in results:
            tid = str(item.get("ticket_id") or "")
            src = by_id.get(tid) or {}
            item["description"] = src.get("description") or ""
            item["tags"] = src.get("tags") or ""
            item["requester_email"] = src.get("requester_email") or ""
        return JSONResponse(
            {
                "ok": True,
                "results": results,
                "processed_rows": len(rows),
                "warning_count": warns,
                "rule_id": candidate.id,
            }
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.post("/rules/disable", response_class=RedirectResponse)
async def rules_disable(rule_id: str = Form(...)) -> RedirectResponse:
    if not portal_allow_confirm():
        return RedirectResponse(url="/rules?error=forbidden", status_code=303)
    repo_root = _repo_root()
    live = ensure_live_bootstrapped(repo_root)
    try:
        disable_explicit_rule(live, rule_id)
    except PromoteError:
        return RedirectResponse(url="/rules?error=disable", status_code=303)
    try_sync_live_to_drive(live)
    _sync_runtime_classifier(repo_root)
    return RedirectResponse(url="/rules?disabled=1", status_code=303)
