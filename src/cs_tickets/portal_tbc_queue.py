"""TBC review queue — Christine-style chunked manual review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cs_tickets.classifier_rules import RuleSpec
from cs_tickets.classify import (
    DEFAULT_TBC,
    classify_row_with_explanation,
    portal_reason_bucket,
)
from cs_tickets.portal_classify_context import (
    quote_snippet,
    suggested_tier_label,
    why_tbc_label,
)
from cs_tickets.portal_explain import explain_ticket_payload
from cs_tickets.portal_stats import classify_run_counts, is_manual_review_row
from cs_tickets.schema import TIER_COLUMNS
from cs_tickets.taxonomy import AllowList
from cs_tickets.tbc_queue_filters import (
    TbcQueueFilter,
    build_tbc_filter_facets,
    filter_pending_tbc_rows,
)
from cs_tickets.thread_enrich import strip_enrichment

DEFAULT_CHUNK_SIZE = 10


@dataclass(frozen=True)
class ReclassifyResult:
    tbc_before: int
    tbc_after: int
    total: int
    warns: int


def _esc(v: object) -> str:
    if v is None:
        return ""
    return (
        str(v)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def pending_tbc_rows(
    rows: list[dict[str, Any]],
    *,
    acked_ids: set[str],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not is_manual_review_row(row):
            continue
        tid = str(row.get("id") or "")
        if tid in acked_ids:
            continue
        out.append(row)
    return out


def build_queue_row_payload(
    row: dict[str, Any],
    allow: AllowList,
    rule_specs: tuple[RuleSpec, ...],
    *,
    tbc_reason_code: str | None = None,
    explain: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explain_payload = explain or explain_ticket_payload(row, allow, rule_specs=rule_specs)
    tid = str(row.get("id") or "")
    assigned_path = _tier_path_label(row)
    candidate_path = ""
    cands = explain_payload.get("candidates") or []
    if cands:
        raw = cands[0].get("tier")
        if isinstance(raw, list) and raw:
            candidate_path = " → ".join(str(x) for x in raw[:4])
    return {
        "ticket_id": tid,
        "subject": str(row.get("subject") or ""),
        "quote": quote_snippet(row),
        "why_tbc": why_tbc_label(explain_payload, tbc_reason_code=tbc_reason_code),
        "suggested_tier": explain_payload.get("suggested_tier") or suggested_tier_label(explain_payload),
        "assigned_tier_path": assigned_path,
        "candidate_tier_path": candidate_path,
    }


def _tier_path_label(row: dict[str, Any]) -> str:
    return " → ".join(str(row.get(col) or "") for col in TIER_COLUMNS[:4])


def build_tbc_queue_payload(
    *,
    run_id: str,
    rows: list[dict[str, Any]],
    tbc_reasons: dict[str, str],
    acked_ids: set[str],
    allow: AllowList,
    rule_specs: tuple[RuleSpec, ...],
    offset: int = 0,
    limit: int = DEFAULT_CHUNK_SIZE,
    queue_filter: TbcQueueFilter | None = None,
    include_facets: bool = False,
) -> dict[str, Any]:
    filt = queue_filter or TbcQueueFilter()
    all_pending = pending_tbc_rows(rows, acked_ids=acked_ids)
    total_pending_unfiltered = len(all_pending)
    if include_facets:
        facets = build_tbc_filter_facets(
            all_pending,
            allow,
            rule_specs,
            tbc_reasons=tbc_reasons,
        )
    else:
        facets = None

    matched = filter_pending_tbc_rows(
        all_pending,
        allow,
        rule_specs,
        filt,
        tbc_reasons=tbc_reasons,
    )
    total_pending = len(matched)
    chunk = matched[offset : offset + limit]
    chunk_rows: list[dict[str, Any]] = []
    for row, explain in chunk:
        tid = str(row.get("id") or "")
        payload = build_queue_row_payload(
            row,
            allow,
            rule_specs,
            tbc_reason_code=tbc_reasons.get(tid),
            explain=explain,
        )
        payload["explain_url"] = f"/run/{run_id}/explain/{tid}?format=json"
        payload["propose_rule_url"] = (
            f"/rules/new?run_id={run_id}&ticket_id={tid}"
        )
        chunk_rows.append(payload)
    chunk_index = (offset // limit) + 1 if limit else 1
    chunk_total = max(1, (total_pending + limit - 1) // limit) if total_pending else 1
    counts = classify_run_counts(rows)
    result: dict[str, Any] = {
        "run_id": run_id,
        "offset": offset,
        "limit": limit,
        "total_pending": total_pending,
        "total_pending_unfiltered": total_pending_unfiltered,
        "total_tbc": counts.tbc,
        "chunk_index": chunk_index,
        "chunk_total": chunk_total,
        "rows": chunk_rows,
        "has_prev": offset > 0,
        "has_next": offset + limit < total_pending,
        "prev_offset": max(0, offset - limit),
        "next_offset": offset + limit,
        "filter": filt.as_dict(),
    }
    if facets is not None:
        result["facets"] = facets
    return result


def reclassify_master_row(
    row: dict[str, Any],
    allow: AllowList,
    rule_specs: tuple[RuleSpec, ...],
) -> tuple[dict[str, Any], str | None, str]:
    """Re-run classifier on a stored master row; return row, optional warn, reason bucket."""
    decision = classify_row_with_explanation(row, allow, rule_specs=rule_specs)
    tier = decision.tier
    warn: str | None = None
    if tier not in allow:
        tier = DEFAULT_TBC if DEFAULT_TBC in allow.tuples else next(iter(sorted(allow.tuples)))
        warn = "tier_coerced_not_in_allowlist"
    out = dict(row)
    for col, val in zip(TIER_COLUMNS, tier, strict=True):
        out[col] = val
    final = tuple(out[c] for c in TIER_COLUMNS)
    if final not in allow.tuples:
        warn = warn or "tier_still_invalid"
    out = strip_enrichment(out)
    reason = portal_reason_bucket(decision, output_row=out)
    return out, warn, reason


def reclassify_run_rows(
    rows: list[dict[str, Any]],
    allow: AllowList,
    rule_specs: tuple[RuleSpec, ...],
) -> tuple[list[dict[str, Any]], dict[str, str], int]:
    updated: list[dict[str, Any]] = []
    tbc_reasons: dict[str, str] = {}
    warns = 0
    for row in rows:
        out, warn, reason = reclassify_master_row(row, allow, rule_specs)
        if warn:
            warns += 1
        tid = str(out.get("id") or "")
        tbc_reasons[tid] = reason
        updated.append(out)
    return updated, tbc_reasons, warns


def tbc_queue_page_html(
    *,
    run_id: str,
    total_pending: int,
    total_tbc: int,
    reclassify_banner: str = "",
    auto_suggest: bool = False,
    llm_available: bool = False,
    can_confirm: bool = False,
    can_add_allowlist: bool = False,
) -> str:
    cta = ""
    if total_pending:
        cta = (
            f'<p class="meta tbc-queue-meta">'
            f"<strong>{total_pending}</strong> ticket"
            f"{'s' if total_pending != 1 else ''} awaiting review "
            f"({total_tbc} manual review in run).</p>"
        )
    else:
        cta = (
            '<p class="run-summary" role="status">'
            "No pending TBC tickets in this queue "
            '(acknowledged chunks are hidden; re-classify after new rules).</p>'
        )
    llm_note = ""
    if llm_available:
        llm_note = (
            '<p class="meta tbc-queue-llm-note">'
            "AI category suggestions run automatically for each chunk "
            f"({'on' if auto_suggest else 'off — enable TBC_AUTO_SUGGEST=1'})."
            "</p>"
        )
    else:
        llm_note = (
            '<p class="meta tbc-queue-llm-note">'
            "Configure RULE_COMPILE API key for AI category suggestions. "
            "Classifier hints only until then."
            "</p>"
        )
    return f"""
    <h1 class="page-header">Manual review queue</h1>
    <p class="links">
      <a href="/run/{_esc(run_id)}/results" class="btn btn-secondary">← Run results</a>
      <button type="button" class="btn btn-secondary" id="tbc-reclassify-btn">Re-classify run</button>
    </p>
    {reclassify_banner}
    {cta}
    {llm_note}
    <div id="tbc-queue-app" class="tbc-queue-app"
      data-run-id="{_esc(run_id)}"
      data-auto-suggest="{"true" if auto_suggest else "false"}"
      data-llm-available="{"true" if llm_available else "false"}"
      data-can-confirm="{"true" if can_confirm else "false"}"
      data-can-add-allowlist="{"true" if can_add_allowlist else "false"}">
      <div class="tbc-queue-toolbar">
        <div class="tbc-filter-bar" id="tbc-filter-bar">
          <label class="tbc-filter-field">
            <span class="tbc-filter-label">Contains</span>
            <input type="search" id="tbc-filter-q" class="tbc-filter-input" placeholder="e.g. sherina, stripe, renew" autocomplete="off" />
          </label>
          <label class="tbc-filter-field">
            <span class="tbc-filter-label">Segment</span>
            <select id="tbc-filter-tier1" class="tbc-filter-select">
              <option value="">All segments</option>
              <option value="B2C">B2C</option>
              <option value="B2B">B2B</option>
            </select>
          </label>
          <label class="tbc-filter-field tbc-filter-field--wide">
            <span class="tbc-filter-label">Category focus</span>
            <input type="text" id="tbc-filter-categories" class="tbc-filter-input" placeholder="e.g. Access Loop, Cancellation, Print" autocomplete="off" />
          </label>
          <button type="button" class="btn btn-secondary btn-sm" id="tbc-filter-clear">Clear</button>
          <button type="button" class="btn btn-secondary btn-sm" id="tbc-filter-draft-rule" hidden>Draft rule for filter</button>
        </div>
        <div id="tbc-filter-rule-panel" class="tbc-filter-rule-panel" hidden>
          <h4>Batch rule draft</h4>
          <textarea id="tbc-filter-rule-text" class="tbc-rule-input" rows="5"></textarea>
          <div class="tbc-rule-actions">
            <button type="button" class="btn btn-secondary btn-sm" id="tbc-filter-rule-compile">Compile</button>
            <button type="button" class="btn btn-secondary btn-sm" id="tbc-filter-rule-preview" disabled>Preview on focus</button>
            {"<button type=\"button\" class=\"btn btn-primary btn-sm\" id=\"tbc-filter-rule-confirm\" disabled>Confirm live</button>" if can_confirm else "<span class=\"meta\">Team lead confirms live rules.</span>"}
          </div>
          <div id="tbc-filter-rule-review" class="meta tbc-rule-review" hidden></div>
          <div id="tbc-filter-rule-preview-results" class="tbc-rule-preview-results" hidden></div>
        </div>
        <div class="tbc-queue-chunk-row">
        <label class="tbc-queue-chunk-label" for="tbc-chunk-size">Chunk size</label>
        <select id="tbc-chunk-size" class="tbc-chunk-size">
          <option value="10" selected>10</option>
          <option value="5">5</option>
          <option value="20">20</option>
        </select>
        <span id="tbc-queue-progress" class="tbc-queue-progress meta" aria-live="polite"></span>
        </div>
      </div>
      <div id="tbc-queue-table-wrap"></div>
      <div id="tbc-completion-panel" class="tbc-completion-panel" hidden></div>
      <div class="tbc-batch-toolbar" id="tbc-batch-toolbar"{"" if can_confirm else " hidden"}>
        <button type="button" class="btn btn-secondary btn-sm" id="tbc-batch-compile" {"disabled" if not llm_available else ""}>
          Compile draft rules in chunk
        </button>
        <button type="button" class="btn btn-primary btn-sm" id="tbc-batch-confirm" disabled>
          Confirm all compiled (0)
        </button>
        <span id="tbc-batch-status" class="meta tbc-batch-status" aria-live="polite"></span>
      </div>
      <div class="tbc-queue-nav">
        <button type="button" class="btn btn-secondary" id="tbc-prev-chunk" disabled>Previous</button>
        <button type="button" class="btn btn-secondary" id="tbc-next-chunk" disabled>Next chunk</button>
        <button type="button" class="btn btn-secondary" id="tbc-ack-chunk">Skip chunk — no rule needed</button>
        <a href="/run/{_esc(run_id)}/results" class="btn btn-primary" id="tbc-finish-btn">Finish → run results</a>
      </div>
    </div>
    """
