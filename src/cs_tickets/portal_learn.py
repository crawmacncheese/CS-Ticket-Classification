"""CS-friendly HTML for Learn New proposal tables."""

from __future__ import annotations

import hashlib

from cs_tickets.allowlist_compare import AllowlistCompareResult, compare_result_html
from cs_tickets.batch_allowlist_analysis import BatchCompareResult
from cs_tickets.feedback.ids import normalize_ticket_id
from cs_tickets.feedback.models import RuleProposal, TaxonomyProposal
from cs_tickets.feedback.parse import LearnParseResult
from cs_tickets.feedback.promote import ConfirmResult
from cs_tickets.portal_training import training_changed_rows_html, training_verdict_banner_html
from cs_tickets.portal_training_copy import (
    CANCEL_LABEL,
    PREVIEW_BUTTON,
    PREVIEW_HELP,
    PREVIEW_LOADING,
    PREVIEW_NO_OP_LABEL,
    PREVIEW_RESULTS_HEADING,
    PREVIEW_STEP_HEADING,
)

_MAX_RULE_ROWS = 40
_MAX_TAX_ROWS = 30

_NOVELTY_LABELS = {
    "tier4_new": "New Tier 4 type",
    "tier3_new": "New Tier 3 category",
    "tier1_new": "New segment — needs review",
    "granular_new": "New granular type",
    "path_new": "New category path",
}


def rule_trigger_plain(proposal: RuleProposal) -> str:
    if proposal.all_tags:
        tags = ", ".join(proposal.all_tags)
        return f"Tagged with all of: {tags}"
    if proposal.any_tags:
        return f"Tagged with: {proposal.any_tags[0]}"
    if proposal.any_subject:
        return f'Subject begins with “{proposal.any_subject[0]}”'
    if proposal.any_blob:
        return f'Message mentions “{proposal.any_blob[0]}”'
    return "—"


def match_consistency_plain(proposal: RuleProposal) -> str:
    if proposal.purity >= 0.999:
        return "All same category"
    pct = int(round(proposal.purity * 100))
    return f"{pct}% same category"


def novelty_plain(proposal: TaxonomyProposal) -> str:
    return _NOVELTY_LABELS.get(proposal.novelty_type, "New category path")


def _h(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _cell_class(col_index: int, *, num_cols: set[int], selectable: bool) -> str:
    if selectable and col_index == 0:
        return "chk"
    return "num" if col_index in num_cols else "txt"


def _example_ids(ids: tuple[str, ...], limit: int = 3) -> str:
    if not ids:
        return "—"
    shown = ", ".join(normalize_ticket_id(i) for i in ids[:limit])
    if len(ids) > limit:
        return f"{shown} (+{len(ids) - limit} more)"
    return shown


def _table_headers_html(headers: list[str], *, selectable: bool) -> str:
    parts: list[str] = []
    if selectable:
        parts.append('<th class="chk"></th>')
    for label in headers:
        parts.append(f"<th>{_h(label)}</th>")
    return "".join(parts)


def _learn_select_actions_html(checkbox_name: str) -> str:
    name = _h(checkbox_name)
    return f"""<p class="training-select-actions">
        <button type="button" class="btn btn-secondary learn-select-all-btn" data-checkbox-name="{name}">Select all</button>
        <button type="button" class="btn btn-secondary learn-select-none-btn" data-checkbox-name="{name}">Select none</button>
    </p>"""


def _row_checkbox_html(*, name: str, proposal_id: str, checked: bool = True) -> str:
    checked_attr = " checked" if checked else ""
    return (
        f'<input type="checkbox" class="learn-row-chk" name="{_h(name)}" '
        f'value="{_h(proposal_id)}"{checked_attr}>'
    )


def learn_selection_hash(
    rule_ids: frozenset[str],
    tax_ids: frozenset[str],
) -> str:
    parts = sorted(rule_ids) + sorted(tax_ids)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


_LEARN_SELECT_ALL_SCRIPT = """
<script>
(function () {
  function updatePreviewBtn() {
    var btn = document.getElementById('learn-preview-btn');
    if (!btn) return;
    var any = document.querySelectorAll('#learn-confirm-form input.learn-row-chk:checked').length > 0;
    btn.disabled = !any;
  }
  document.querySelectorAll('.learn-select-all-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var name = btn.getAttribute('data-checkbox-name');
      document.querySelectorAll('input.learn-row-chk[name="' + name + '"]').forEach(function (cb) {
        cb.checked = true;
      });
      updatePreviewBtn();
    });
  });
  document.querySelectorAll('.learn-select-none-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var name = btn.getAttribute('data-checkbox-name');
      document.querySelectorAll('input.learn-row-chk[name="' + name + '"]').forEach(function (cb) {
        cb.checked = false;
      });
      updatePreviewBtn();
    });
  });
  document.querySelectorAll('.learn-row-chk').forEach(function (cb) {
    cb.addEventListener('change', updatePreviewBtn);
  });
  updatePreviewBtn();
})();
</script>
""".strip()


def rule_proposals_table_html(
    proposals: tuple[RuleProposal, ...],
    *,
    selectable: bool = False,
    checked_ids: frozenset[str] | None = None,
) -> str:
    headers = [
        "When tickets…",
        "Tier1_Segment",
        "Tier2_Stream",
        "Tier3_Cat",
        "Tier4_Type",
        "COUNTA of id",
        "Consistency",
        "Example ticket ids",
    ]
    num_cols = {6 if selectable else 5}
    th = _table_headers_html(headers, selectable=selectable)
    trs: list[str] = []
    for i, proposal in enumerate(proposals[:_MAX_RULE_ROWS]):
        t1, t2, t3, t4, _granular = proposal.tier
        cells: list[str] = [
            rule_trigger_plain(proposal),
            t1,
            t2,
            t3,
            t4,
            str(proposal.support),
            match_consistency_plain(proposal),
            _example_ids(proposal.evidence_ids),
        ]
        if selectable:
            is_checked = checked_ids is None or proposal.proposal_id in checked_ids
            cells = [
                _row_checkbox_html(
                    name="rule_ids",
                    proposal_id=proposal.proposal_id,
                    checked=is_checked,
                ),
                *cells,
            ]
        row_cls = "zebra-even" if i % 2 == 1 else "zebra-odd"
        tds_parts: list[str] = []
        for j, cell in enumerate(cells):
            cls = _cell_class(j, num_cols=num_cols, selectable=selectable)
            if selectable and j == 0:
                tds_parts.append(f"<td class='{cls}'>{cell}</td>")
            else:
                tds_parts.append(f"<td class='{cls}'>{_h(cell)}</td>")
        trs.append(f"<tr class='{row_cls}'>{''.join(tds_parts)}</tr>")

    return f"""
<table class="stats-table" aria-label="Suggested classification rules">
  <thead><tr>{th}</tr></thead>
  <tbody>
    {"".join(trs)}
  </tbody>
</table>
""".strip()


def taxonomy_proposals_table_html(
    proposals: tuple[TaxonomyProposal, ...],
    *,
    selectable: bool = False,
    checked_ids: frozenset[str] | None = None,
) -> str:
    headers = [
        "Tier1_Segment",
        "Tier2_Stream",
        "Tier3_Cat",
        "Tier4_Type",
        "COUNTA of id",
        "What's new",
        "Example ticket ids",
    ]
    num_cols = {5 if selectable else 4}

    sorted_items = sorted(proposals[:_MAX_TAX_ROWS], key=lambda p: p.tier[:4])
    prev: tuple[str | None, str | None, str | None, str | None] = (None, None, None, None)
    th = _table_headers_html(headers, selectable=selectable)
    trs: list[str] = []
    for i, proposal in enumerate(sorted_items):
        t1, t2, t3, t4, _granular = proposal.tier
        c1 = t1 if prev[0] is None or t1 != prev[0] else ""
        c2 = t2 if prev[0] is None or t1 != prev[0] or t2 != prev[1] else ""
        c3 = t3 if prev[0] is None or t1 != prev[0] or t2 != prev[1] or t3 != prev[2] else ""
        c4 = t4
        cells: list[str] = [
            c1,
            c2,
            c3,
            c4,
            str(proposal.count),
            novelty_plain(proposal),
            _example_ids(proposal.evidence_ids),
        ]
        if selectable:
            is_checked = checked_ids is None or proposal.proposal_id in checked_ids
            cells = [
                _row_checkbox_html(
                    name="tax_ids",
                    proposal_id=proposal.proposal_id,
                    checked=is_checked,
                ),
                *cells,
            ]
        row_cls = "zebra-even" if i % 2 == 1 else "zebra-odd"
        tds_parts: list[str] = []
        for j, cell in enumerate(cells):
            cls = _cell_class(j, num_cols=num_cols, selectable=selectable)
            if selectable and j == 0:
                tds_parts.append(f"<td class='{cls}'>{cell}</td>")
            else:
                tds_parts.append(f"<td class='{cls}'>{_h(cell)}</td>")
        trs.append(f"<tr class='{row_cls}'>{''.join(tds_parts)}</tr>")
        prev = (t1, t2, t3, t4)

    return f"""
<table class="stats-table" aria-label="New category paths to add">
  <thead><tr>{th}</tr></thead>
  <tbody>
    {"".join(trs)}
  </tbody>
</table>
""".strip()


def _drive_status_html(
    *,
    drive_live_url: str | None = None,
    drive_files_uploaded: int | None = None,
    drive_error: str | None = None,
    drive_skip_reason: str | None = None,
) -> str:
    if drive_live_url:
        files_note = ""
        if drive_files_uploaded:
            noun = "file" if drive_files_uploaded == 1 else "files"
            files_note = f" ({drive_files_uploaded} config {noun} synced)"
        return (
            f'<p class="meta drive-ok">Google Drive: '
            f'<a href="{_h(drive_live_url)}" target="_blank" rel="noopener noreferrer">'
            f"Open live folder</a>{files_note}</p>"
        )
    if drive_error:
        return (
            f'<p class="meta drive-warning" role="alert">'
            f"Google Drive upload failed: {_h(drive_error)}</p>"
        )
    if drive_skip_reason:
        return (
            f'<p class="meta drive-warning" role="alert">'
            f"Saved locally only — Drive sync not configured. {_h(drive_skip_reason)}</p>"
        )
    return ""


def learn_confirm_success_html(
    result: ConfirmResult,
    *,
    drive_live_url: str | None = None,
    drive_files_uploaded: int | None = None,
    drive_error: str | None = None,
    drive_skip_reason: str | None = None,
) -> str:
    drive_line = _drive_status_html(
        drive_live_url=drive_live_url,
        drive_files_uploaded=drive_files_uploaded,
        drive_error=drive_error,
        drive_skip_reason=drive_skip_reason,
    )
    return f"""<p class="run-summary" role="status">
        <span class="run-summary-lead">Live — config version {result.config_version_after}</span>
        <span class="run-summary-meta">({result.rules_added} rules · {result.taxonomy_added} category paths applied)</span>
    </p>
    <p class="meta learn-ok">
        Proposal <code>{_h(result.proposal_id)}</code> saved.
        The <strong>next categorisation run</strong> will use these changes.
    </p>
    {drive_line}"""


def learn_proposals_html(
    result: LearnParseResult,
    upload_id: str,
    *,
    status: str = "processed",
    confirm_result: ConfirmResult | None = None,
    drive_live_url: str | None = None,
    drive_files_uploaded: int | None = None,
    drive_error: str | None = None,
    drive_skip_reason: str | None = None,
    checked_rule_ids: frozenset[str] | None = None,
    checked_tax_ids: frozenset[str] | None = None,
) -> str:
    if status == "live" and confirm_result is not None:
        return learn_confirm_success_html(
            confirm_result,
            drive_live_url=drive_live_url,
            drive_files_uploaded=drive_files_uploaded,
            drive_error=drive_error,
            drive_skip_reason=drive_skip_reason,
        )

    if not result.rule_proposals and not result.taxonomy_proposals:
        return """<p class="meta learn-stub">
        No suggestions met our thresholds (at least 5 similar tickets, mostly the same category).
        Tickets already handled by current rules are not listed here.
        </p>"""

    selectable = status == "processed"
    parts: list[str] = [
        f"""<p class="meta learn-ok">
        We found <strong>{result.rule_proposal_count}</strong> suggested rules and
        <strong>{result.taxonomy_proposal_count}</strong> new category paths.
        <strong>{result.already_classified_count}</strong> tickets already match existing rules and were skipped.
        Review below, uncheck any you do not want, then confirm — nothing is live until you confirm.
        </p>"""
    ]

    form_open = ""
    form_close = ""
    if selectable:
        form_open = f"""<form class="learn-confirm-form" id="learn-confirm-form" action="/learn/confirm" method="post">
            <input type="hidden" name="upload_id" value="{_h(upload_id)}">"""
        form_close = "</form>"

    if result.rule_proposals:
        more = ""
        if len(result.rule_proposals) > _MAX_RULE_ROWS:
            more = (
                f'<p class="meta">Showing first {_MAX_RULE_ROWS} of '
                f"{len(result.rule_proposals)} suggested rules.</p>"
            )
        select_actions = _learn_select_actions_html("rule_ids") if selectable else ""
        parts.append(
            f"""<h2 class="section-header">Suggested rules ({len(result.rule_proposals)})</h2>
            <p class="meta">When a ticket matches the description, assign it to the category shown.</p>
            {more}
            {select_actions}
            <div class="stats-wrap">{rule_proposals_table_html(result.rule_proposals, selectable=selectable, checked_ids=checked_rule_ids)}</div>"""
        )

    if result.taxonomy_proposals:
        select_actions = _learn_select_actions_html("tax_ids") if selectable else ""
        parts.append(
            f"""<h2 class="section-header">New category paths ({len(result.taxonomy_proposals)})</h2>
            <p class="meta">These tier combinations appear in your upload but are not in the current taxonomy.</p>
            {select_actions}
            <div class="stats-wrap">{taxonomy_proposals_table_html(result.taxonomy_proposals, selectable=selectable, checked_ids=checked_tax_ids)}</div>"""
        )

    if selectable and (result.rule_proposals or result.taxonomy_proposals):
        return form_open + "\n".join(parts) + form_close

    return "\n".join(parts)


def learn_confirm_bar_html() -> str:
    return f"""<div class="learn-confirm-bar">
        <p class="meta">Confirm applies to the <strong>next categorisation run</strong> immediately (config version will increment).</p>
        <p class="training-actions">
            <button type="submit" form="learn-confirm-form" class="btn btn-primary">Confirm changes</button>
            <button type="submit" form="learn-confirm-form" formaction="/learn/cancel" class="btn btn-secondary">{CANCEL_LABEL}</button>
            <a href="/learn" class="btn btn-secondary">Upload another</a>
        </p>
    </div>"""


_LEARN_PREVIEW_SCRIPT = """
<script>
(function () {
  var previewForm = document.getElementById('learn-preview-form');
  if (!previewForm) return;
  previewForm.addEventListener('submit', function () {
    var container = document.getElementById('learn-preview-selection');
    if (!container) return;
    container.innerHTML = '';
    document.querySelectorAll('#learn-confirm-form input.learn-row-chk:checked').forEach(function (cb) {
      var input = document.createElement('input');
      input.type = 'hidden';
      input.name = cb.name;
      input.value = cb.value;
      container.appendChild(input);
    });
  });
})();
</script>
""".strip()


def learn_preview_results_html(
    *,
    batch_result: BatchCompareResult | None = None,
    compare_result: AllowlistCompareResult | None = None,
    stale: bool = False,
) -> str:
    if stale:
        return (
            '<p class="training-stale-banner" role="status">'
            "Selection changed — re-run preview to update metrics.</p>"
        )
    if batch_result is None and compare_result is None:
        return ""
    parts: list[str] = []
    if batch_result is not None:
        parts.append(training_verdict_banner_html(batch_result))
    if compare_result is not None:
        parts.append(compare_result_html(compare_result, stale=False, plain_language=True))
        if compare_result.changed_rows:
            parts.append('<h3 class="section-header">Changed tickets</h3>')
            parts.append(training_changed_rows_html(compare_result.changed_rows))
    return "\n".join(parts)


def learn_preview_panel_html(
    upload_id: str,
    result: LearnParseResult,
    *,
    batch_result: BatchCompareResult | None = None,
    compare_result: AllowlistCompareResult | None = None,
    preview_stale: bool = False,
    bad_satisfaction_only: bool = False,
    compute_no_op: bool = False,
) -> str:
    if not result.rule_proposals and not result.taxonomy_proposals:
        return ""
    bad_csat_checked = " checked" if bad_satisfaction_only else ""
    no_op_checked = " checked" if compute_no_op else ""
    results = learn_preview_results_html(
        batch_result=batch_result,
        compare_result=compare_result,
        stale=preview_stale,
    )
    results_block = ""
    if results:
        results_block = f"""
    <div class="learn-preview-results">
        <h3 class="section-header">{PREVIEW_RESULTS_HEADING}</h3>
        {results}
    </div>"""
    return f"""
<section class="learn-preview-section">
    <h2 class="section-header">{PREVIEW_STEP_HEADING}</h2>
    <p class="meta">{PREVIEW_HELP}</p>
    <div class="upload-card-wrap">
        <div class="upload-card training-preview-card">
            <form action="/learn/preview" method="post" enctype="multipart/form-data"
                  class="training-preview-form" id="learn-preview-form" data-loading-form>
                <input type="hidden" name="upload_id" value="{_h(upload_id)}">
                <div id="learn-preview-selection"></div>
                <div class="training-preview-options">
                    <input type="file" name="preview_file" class="file-input training-preview-file"
                           accept=".json,.ndjson" required>
                    <label class="filter-option">
                        <input type="checkbox" name="bad_satisfaction_only" value="true"{bad_csat_checked}>
                        Only preview tickets with bad CSAT rating
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" name="compute_no_op" value="true"{no_op_checked}>
                        {PREVIEW_NO_OP_LABEL}
                    </label>
                    <button type="submit" class="btn btn-secondary" id="learn-preview-btn"
                            data-loading-btn data-loading-label="{PREVIEW_LOADING}" disabled>{PREVIEW_BUTTON}</button>
                </div>
            </form>
        </div>
    </div>
    {results_block}
</section>""".strip()


def learn_process_body_html(
    result: LearnParseResult,
    upload_id: str,
    *,
    checked_rule_ids: frozenset[str] | None = None,
    checked_tax_ids: frozenset[str] | None = None,
    batch_result: BatchCompareResult | None = None,
    compare_result: AllowlistCompareResult | None = None,
    preview_stale: bool = False,
    bad_satisfaction_only: bool = False,
    compute_no_op: bool = False,
) -> str:
    proposals = learn_proposals_html(
        result,
        upload_id,
        status="processed",
        checked_rule_ids=checked_rule_ids,
        checked_tax_ids=checked_tax_ids,
    )
    preview = learn_preview_panel_html(
        upload_id,
        result,
        batch_result=batch_result,
        compare_result=compare_result,
        preview_stale=preview_stale,
        bad_satisfaction_only=bad_satisfaction_only,
        compute_no_op=compute_no_op,
    )
    confirm_bar = ""
    scripts = ""
    if result.rule_proposals or result.taxonomy_proposals:
        confirm_bar = learn_confirm_bar_html()
        scripts = _LEARN_SELECT_ALL_SCRIPT + "\n" + _LEARN_PREVIEW_SCRIPT
    return f"{proposals}\n{preview}\n{confirm_bar}\n{scripts}"


def learn_revert_footer_html(*, show_revert: bool) -> str:
    if not show_revert:
        return ""
    return """
<p class="meta learn-revert-note">Undo restores the previous live config (taxonomy, workbook, rules).</p>
<form action="/learn/revert" method="post" class="training-revert-form">
    <button type="submit" class="btn btn-secondary">Undo last confirm</button>
</form>""".strip()
