from __future__ import annotations

import json
from pathlib import Path

from cs_tickets.allowlist_compare import AllowlistCompareResult, compare_result_html
from cs_tickets.allowlist_training import (
    _TrainingSession,
    preview_is_stale,
)
from cs_tickets.batch_allowlist_analysis import BatchCompareResult
from cs_tickets.classifier_rules import load_rule_specs
from cs_tickets.portal_training_copy import (
    CANCEL_LABEL,
    DESELECT_NO_OP_BUTTON,
    DONE_LABEL,
    GRANULAR_VARIANT_BADGE,
    IMPACT_COLUMN_HEADING,
    IMPACT_NO_EFFECT,
    IMPACT_NOT_ANALYZED,
    IMPACT_SUMMARY,
    IMPACT_WOULD_CHANGE,
    PREVIEW_BUTTON,
    PREVIEW_HELP,
    PREVIEW_LOADING,
    PREVIEW_NO_OP_LABEL,
    PREVIEW_RESULTS_HEADING,
    PREVIEW_STEP_HEADING,
    REVIEW_HELP,
    REVIEW_INTRO_MANY,
    REVIEW_INTRO_ONE,
    REVIEW_STEP_HEADING,
    SAVE_SELECTED_LABEL,
    SHOW_CHANGE_DETAILS_LABEL,
    STEP_LABELS,
    TRAINING_CANCEL_TITLE,
    TRAINING_REVERT_TITLE,
    TRAINING_REVIEW_TITLE,
    TRAINING_SUCCESS_TITLE,
    TRAINING_TITLE,
    UNDO_FOOTNOTE,
    UNDO_LAST_SAVE,
    BACK_TO_CLASSIFY_LABEL,
    UPLOAD_BUTTON,
    UPLOAD_INTRO,
    UPLOAD_LOADING,
    UPLOAD_STEP_HEADING,
    VERDICT_MESSAGES,
)
from cs_tickets.rule_coverage import computed_rule_targets, training_routing_badge, training_routing_badge_label
from cs_tickets.taxonomy import AllowList

_GOLDEN_BASELINE_PATH = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "golden_baseline.json"
)


def encode_tuple(t: tuple[str, str, str, str, str]) -> str:
    return "|".join(t)


def decode_tuple(raw: str) -> tuple[str, str, str, str, str]:
    parts = raw.split("|")
    if len(parts) != 5:
        raise ValueError(f"Expected 5-tier tuple, got {len(parts)} parts")
    return tuple(parts)


def parse_selected_tuples(values: list[str]) -> frozenset[tuple[str, str, str, str, str]]:
    return frozenset(decode_tuple(v) for v in values if v.strip())


def granular_variant_hint(
    tup: tuple[str, str, str, str, str],
    allow: AllowList,
) -> str | None:
    na_tuple = tup[:4] + ("N/A",)
    if tup[4] != "N/A" and na_tuple in allow.tuples:
        return GRANULAR_VARIANT_BADGE
    return None


def _category_path_html(tup: tuple[str, str, str, str, str]) -> str:
    main = " &rarr; ".join(_esc(v) for v in tup[:4])
    granular = tup[4]
    if granular and granular != "N/A":
        return (
            f'<span class="category-path-main">{main}</span>'
            f'<span class="category-path-granular">{_esc(granular)}</span>'
        )
    return f'<span class="category-path-main">{main}</span>'


def training_wizard_html(active_step: int) -> str:
    items = []
    for i, label in enumerate(STEP_LABELS, start=1):
        classes = ["wizard-step"]
        if i < active_step:
            classes.append("wizard-step--done")
        elif i == active_step:
            classes.append("wizard-step--active")
        items.append(f'<li class="{" ".join(classes)}">{i}. {_esc(label)}</li>')
    return f"""
<nav class="training-wizard" aria-label="Training progress">
  <ol>{"".join(items)}</ol>
</nav>"""


def training_checklist_html(
    session: _TrainingSession,
    selected: frozenset[tuple[str, str, str, str, str]],
    *,
    allow: AllowList,
) -> str:
    if not session.new_tuples:
        return f"""
        <div class="training-checklist training-no-new-tuples">
            <p class="meta training-info" role="status">
                No new categories found — everything in your upload is already in the reference list.</p>
            <form method="post" class="training-dismiss-form">
                <input type="hidden" name="session_id" value="{_esc(session.session_id)}">
                <p class="training-actions">
                    <button type="submit" formaction="/training/cancel" class="btn btn-secondary">{DONE_LABEL}</button>
                    <a href="/" class="btn btn-secondary">Back to categorize</a>
                </p>
            </form>
        </div>"""

    rules = load_rule_specs()
    computed = computed_rule_targets()
    stale = preview_is_stale(session, selected)
    show_impact = (
        session.preview_compute_no_op
        and session.preview_batch_result is not None
        and not stale
    )
    no_op_in_selection = session.preview_no_op_tuples & selected if show_impact else frozenset()
    deselect_no_op = ""
    if show_impact and no_op_in_selection:
        deselect_no_op = (
            f'<button type="button" class="btn btn-secondary" id="deselect-no-op-tuples">'
            f"{DESELECT_NO_OP_BUTTON}</button>"
        )

    impact_summary = ""
    if show_impact and selected:
        impactful_n = len(selected - session.preview_no_op_tuples)
        no_op_n = len(no_op_in_selection)
        impact_summary = (
            f'<p class="meta impact-summary">{IMPACT_SUMMARY.format(impactful=impactful_n, no_op=no_op_n, total=len(selected))}</p>'
        )

    impact_header = f"<th>{IMPACT_COLUMN_HEADING}</th>" if show_impact else ""
    rows = ""
    for tup in sorted(session.new_tuples):
        encoded = encode_tuple(tup)
        checked = " checked" if tup in selected else ""
        count = session.ticket_counts.get(tup, 0)
        path = _category_path_html(tup)
        badge = training_routing_badge_label(
            training_routing_badge(tup, json_rules=rules, computed_targets=computed)
        )
        granular_badge = ""
        hint = granular_variant_hint(tup, allow)
        if hint:
            granular_badge = f' <span class="granular-variant-badge">{_esc(hint)}</span>'
        row_class = ""
        impact_cell = ""
        if show_impact:
            if tup in selected:
                if tup in session.preview_no_op_tuples:
                    row_class = ' class="tuple-row tuple-row--no-op"'
                    impact_cell = (
                        f'<td><span class="impact-badge impact--none">{IMPACT_NO_EFFECT}</span></td>'
                    )
                else:
                    row_class = ' class="tuple-row tuple-row--impactful"'
                    impact_cell = (
                        f'<td><span class="impact-badge impact--yes">{IMPACT_WOULD_CHANGE}</span></td>'
                    )
            else:
                row_class = ' class="tuple-row"'
                impact_cell = (
                    f'<td><span class="impact-badge impact--na">{IMPACT_NOT_ANALYZED}</span></td>'
                )
        rows += (
            f'<tr{row_class}><td><input type="checkbox" name="selected_tuple" value="{_esc(encoded)}"{checked} '
            f'class="tuple-checkbox" data-tuple="{_esc(encoded)}"></td>'
            f'<td class="category-path-cell">{path}{granular_badge}</td><td>{count}</td>'
            f'<td><span class="coverage-badge">{_esc(badge)}</span></td>{impact_cell}</tr>'
        )

    session_id = _esc(session.session_id)
    return f"""
    <div class="training-checklist">
        <p class="meta">{REVIEW_HELP}</p>
        {impact_summary}
        <form method="post" class="training-main-form" id="training-main-form">
            <input type="hidden" name="session_id" value="{session_id}">
            <p class="training-select-actions">
                <button type="button" class="btn btn-secondary" id="select-all-tuples">Select all</button>
                <button type="button" class="btn btn-secondary" id="select-none-tuples">Select none</button>
                {deselect_no_op}
            </p>
            <table class="preview-table training-tuple-table">
                <thead><tr><th></th><th>Category path</th><th>Tickets in upload</th><th>Coverage</th>{impact_header}</tr></thead>
                <tbody>{rows}</tbody>
            </table>
            <p class="training-actions">
                <button type="submit" formaction="/training/commit" class="btn btn-primary" id="training-commit-btn" disabled>{SAVE_SELECTED_LABEL}</button>
                <button type="submit" formaction="/training/cancel" class="btn btn-secondary">{CANCEL_LABEL}</button>
                <a href="/" class="btn btn-secondary">Back to categorize</a>
            </p>
        </form>
        {training_preview_controls_html(session)}
    </div>"""


def training_preview_controls_html(session: _TrainingSession) -> str:
    bad_csat_checked = " checked" if session.preview_bad_satisfaction_only else ""
    no_op_checked = " checked" if session.preview_compute_no_op else ""
    return f"""
    <h2 class="section-header">{PREVIEW_STEP_HEADING}</h2>
    <p class="meta">{PREVIEW_HELP}</p>
    <form action="/training/preview" method="post" enctype="multipart/form-data" class="training-preview-form" id="training-preview-form" data-loading-form>
        <input type="hidden" name="session_id" value="{_esc(session.session_id)}">
        <div id="training-preview-selected-tuples"></div>
        <div class="training-preview-options">
            <input type="file" name="preview_file" class="file-input training-preview-file" accept=".json,.ndjson" required>
            <label class="filter-option">
                <input type="checkbox" name="bad_satisfaction_only" value="true"{bad_csat_checked}>
                Only preview tickets with bad CSAT rating
            </label>
            <label class="filter-option">
                <input type="checkbox" name="compute_no_op" value="true"{no_op_checked}>
                {PREVIEW_NO_OP_LABEL}
            </label>
            <button type="submit" class="btn btn-secondary" id="training-preview-btn" data-loading-btn data-loading-label="{PREVIEW_LOADING}" disabled>{PREVIEW_BUTTON}</button>
        </div>
    </form>
    """


def training_verdict_banner_html(batch: BatchCompareResult) -> str:
    combined = batch.combined
    label, action = VERDICT_MESSAGES.get(
        batch.verdict_band,
        ("Review changes", "Check the metrics below before saving."),
    )
    net_tbc = combined.tbc_old - combined.tbc_new
    net_sign = "+" if net_tbc > 0 else ""
    gap_fix = batch.outcome_counts.get("gap_fix", 0)
    regression = batch.outcome_counts.get("regression", 0)
    reroute = batch.outcome_counts.get("reroute", 0)
    no_op_line = ""
    if batch.selection_no_op_count is not None and batch.selected_tuples:
        n_sel = len(batch.selected_tuples)
        no_op_line = (
            f"<li>{batch.selection_no_op_count} of {n_sel} selected "
            f"categor{'y' if n_sel == 1 else 'ies'} had no effect on this export</li>"
        )
    return f"""
<div class="verdict-banner verdict--{_esc(batch.verdict_band)}" role="status">
  <p class="verdict-headline">{_esc(label)}</p>
  <p class="verdict-action meta">{_esc(action)}</p>
  <ul class="verdict-stats">
    <li>Preview on {combined.total} tickets: manual review (TBC) {combined.tbc_old} &rarr; {combined.tbc_new} ({net_sign}{net_tbc})</li>
    <li>Gap fixes: {gap_fix} · Regressions: {regression} · Reroutes: {reroute}</li>
    {no_op_line}
  </ul>
</div>"""


def _golden_baseline_hint_html(tbc_count: int, total: int) -> str:
    if not _GOLDEN_BASELINE_PATH.is_file() or total <= 0:
        return ""
    try:
        data = json.loads(_GOLDEN_BASELINE_PATH.read_text(encoding="utf-8"))
        golden_total = int(data.get("total", 0))
        tbc_max = int(data.get("tbc_max", 0))
        if golden_total <= 0:
            return ""
        golden_pct = 100.0 * tbc_max / golden_total
        preview_pct = 100.0 * tbc_count / total
        return (
            f'<p class="meta golden-hint">Fixture reference only: golden sample allows up to '
            f"{tbc_max}/{golden_total} manual review ({golden_pct:.0f}%). "
            f"Your preview: {tbc_count}/{total} ({preview_pct:.1f}%).</p>"
        )
    except (OSError, ValueError, TypeError):
        return ""


def training_changed_rows_html(changed_rows: list[dict], *, limit: int = 50) -> str:
    if not changed_rows:
        return '<p class="meta">No ticket classification changes on this export.</p>'
    sample = changed_rows[:limit]
    rows_html = ""
    for ch in sample:
        outcome = ch.get("outcome_type", "")
        mechanism = ch.get("gap_fix_mechanism") or ""
        reason = ch.get("new_tbc_reason") or ch.get("old_tbc_reason") or ""
        rows_html += (
            f"<tr>"
            f"<td>{_esc(ch.get('id'))}</td>"
            f"<td class='change-col-compact'>{_esc(ch.get('old_tier4'))}</td>"
            f"<td class='change-col-compact'>{_esc(ch.get('new_tier4'))}</td>"
            f"<td class='change-col-detail'>{_esc(outcome)}</td>"
            f"<td class='change-col-detail'>{_esc(mechanism)}</td>"
            f"<td class='change-col-detail'>{_esc(reason)}</td>"
            f"</tr>"
        )
    more = ""
    if len(changed_rows) > limit:
        more = f'<p class="meta">Showing {limit} of {len(changed_rows)} changed tickets.</p>'
    return f"""
<label class="filter-option training-details-toggle">
    <input type="checkbox" id="show-changed-details">
    {SHOW_CHANGE_DETAILS_LABEL}
</label>
<table class="preview-table training-changed-table">
    <thead><tr>
        <th>Ticket id</th>
        <th>Old category</th>
        <th>New category</th>
        <th class="change-col-detail">Outcome</th>
        <th class="change-col-detail">Mechanism</th>
        <th class="change-col-detail">Why (TBC reason)</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
</table>
{more}"""


def training_preview_section_html(
    session: _TrainingSession,
    selected: frozenset[tuple[str, str, str, str, str]],
    result: AllowlistCompareResult | None,
    *,
    batch_result: BatchCompareResult | None = None,
) -> str:
    display = result or session.preview_result
    batch = batch_result or session.preview_batch_result
    if display is None and batch is None:
        return ""

    stale = preview_is_stale(session, selected) if session.preview_result else False
    if stale:
        return (
            f'<h2 class="section-header">{PREVIEW_RESULTS_HEADING}</h2>'
            '<p class="training-stale-banner" role="status">'
            "Selection changed — re-run preview to update metrics.</p>"
        )

    parts = [f'<h2 class="section-header">{PREVIEW_RESULTS_HEADING}</h2>']
    if batch is not None:
        parts.append(training_verdict_banner_html(batch))
        parts.append(_golden_baseline_hint_html(batch.combined.tbc_new, batch.combined.total))
    if display is not None:
        parts.append(compare_result_html(display, stale=False, plain_language=True))
        changed = display.changed_rows
        if changed:
            parts.append("<h3 class=\"section-header\">Changed tickets</h3>")
            parts.append(training_changed_rows_html(changed))
    return "\n".join(parts)


def training_footer_html(*, show_revert: bool, show_back: bool = True) -> str:
    if not show_revert and not show_back:
        return ""
    back = ""
    if show_back:
        back = f'<a href="/" class="btn btn-secondary">{BACK_TO_CLASSIFY_LABEL}</a>'
    revert = ""
    if show_revert:
        revert = f"""
        <form action="/training/revert" method="post" class="training-revert-form">
            <button type="submit" class="btn btn-secondary">{UNDO_LAST_SAVE}</button>
        </form>"""
    footnote = f'<p class="meta training-footer-note">{UNDO_FOOTNOTE}</p>' if show_revert else ""
    return f"""
    <footer class="training-footer">
        <div class="training-footer-actions">
            {back}
            {revert}
        </div>
        {footnote}
    </footer>"""


def training_page_shell(
    *,
    title: str,
    head: str,
    body: str,
    wizard_step: int = 1,
) -> str:
    wizard = training_wizard_html(wizard_step)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>{head}
<script src="/static/training.js?v=2" defer></script>
</head>
<body>
<div class="container training-page">
    <h1 class="page-header">{_esc(title)}</h1>
    {wizard}
    {body}
</div>
</body></html>"""


def training_upload_body_html(*, show_revert: bool) -> str:
    return f"""
    <p class="meta">{UPLOAD_INTRO}</p>
    <h2 class="section-header">{UPLOAD_STEP_HEADING}</h2>
    <div class="upload-card-wrap">
        <div class="upload-card">
            <form action="/training/upload" method="post" enctype="multipart/form-data" class="upload-form training-upload-form" id="training-upload-form" data-loading-form>
                <input type="file" name="workbook" class="file-input" accept=".xlsx" required>
                <button type="submit" class="btn btn-primary" id="training-upload-btn" data-loading-btn data-loading-label="{UPLOAD_LOADING}">{UPLOAD_BUTTON}</button>
            </form>
        </div>
    </div>
    {training_footer_html(show_revert=show_revert, show_back=True)}"""


def review_intro_html(n: int) -> str:
    template = REVIEW_INTRO_ONE if n == 1 else REVIEW_INTRO_MANY
    return f'<p class="meta">{template.format(n=n)}</p>'


def _esc(v: object) -> str:
    if v is None:
        return ""
    s = str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return s
