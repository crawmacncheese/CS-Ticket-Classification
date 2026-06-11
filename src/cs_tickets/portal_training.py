from __future__ import annotations

from cs_tickets.allowlist_compare import AllowlistCompareResult, compare_result_html
from cs_tickets.allowlist_training import (
    _TrainingSession,
    preview_is_stale,
)
from cs_tickets.classifier_rules import load_rule_specs
from cs_tickets.rule_coverage import computed_rule_targets, training_routing_badge, training_routing_badge_label
from cs_tickets.schema import TIER_COLUMNS


def encode_tuple(t: tuple[str, str, str, str, str]) -> str:
    return "|".join(t)


def decode_tuple(raw: str) -> tuple[str, str, str, str, str]:
    parts = raw.split("|")
    if len(parts) != 5:
        raise ValueError(f"Expected 5-tier tuple, got {len(parts)} parts")
    return tuple(parts)


def parse_selected_tuples(values: list[str]) -> frozenset[tuple[str, str, str, str, str]]:
    return frozenset(decode_tuple(v) for v in values if v.strip())


def training_checklist_html(
    session: _TrainingSession,
    selected: frozenset[tuple[str, str, str, str, str]],
) -> str:
    if not session.new_tuples:
        return f"""
        <div class="training-checklist training-no-new-tuples">
            <p class="meta training-info" role="status">
                No new tier combinations found — everything in your upload is already in the allow-list.</p>
            <form method="post" class="training-dismiss-form">
                <input type="hidden" name="session_id" value="{_esc(session.session_id)}">
                <p class="training-actions">
                    <button type="submit" formaction="/training/cancel" class="btn btn-secondary">Done</button>
                    <a href="/" class="btn btn-secondary">Back to classify</a>
                </p>
            </form>
        </div>"""

    rules = load_rule_specs()
    computed = computed_rule_targets()
    rows = ""
    for tup in sorted(session.new_tuples):
        encoded = encode_tuple(tup)
        checked = " checked" if tup in selected else ""
        count = session.ticket_counts.get(tup, 0)
        label = " | ".join(_esc(v) for v in tup)
        badge = training_routing_badge_label(
            training_routing_badge(tup, json_rules=rules, computed_targets=computed)
        )
        rows += (
            f'<tr><td><input type="checkbox" name="selected_tuple" value="{_esc(encoded)}"{checked} '
            f'class="tuple-checkbox"></td>'
            f"<td>{label}</td><td>{count}</td>"
            f'<td><span class="coverage-badge">{_esc(badge)}</span></td></tr>'
        )

    tier_headers = "".join(f"<th>{_esc(c)}</th>" for c in TIER_COLUMNS)
    session_id = _esc(session.session_id)
    return f"""
    <div class="training-checklist">
        <p class="meta">Select tier combinations to add to the allow-list. Each accepted combination adds one exemplar row and, when needed, a matching routing rule. &ldquo;Already routable&rdquo; means a classifier rule targets that category today — the exemplar ticket may still hit margin competition.</p>
        <form method="post" class="training-main-form" id="training-main-form">
            <input type="hidden" name="session_id" value="{session_id}">
            <p class="training-select-actions">
                <button type="button" class="btn btn-secondary" id="select-all-tuples">Select all</button>
                <button type="button" class="btn btn-secondary" id="select-none-tuples">Select none</button>
            </p>
            <table class="preview-table training-tuple-table">
                <thead><tr><th></th>{tier_headers}<th>Tickets in upload</th><th>Coverage</th></tr></thead>
                <tbody>{rows}</tbody>
            </table>
            <p class="training-actions">
                <button type="submit" formaction="/training/commit" class="btn btn-primary" id="training-commit-btn" disabled>Commit selected</button>
                <button type="submit" formaction="/training/cancel" class="btn btn-secondary">Cancel</button>
                <a href="/" class="btn btn-secondary">Back to classify</a>
            </p>
        </form>
        {training_preview_controls_html(session)}
    </div>"""


def training_preview_controls_html(session: _TrainingSession) -> str:
    checked = " checked" if session.preview_bad_satisfaction_only else ""
    return f"""
    <h2 class="section-header">Step 3 — Preview changes (optional)</h2>
    <p class="meta">Select combinations above, then upload a Zendesk JSON/NDJSON export to preview how classification would differ with a candidate allow-list <strong>and matching rules</strong> for your selection — nothing is written to <code>doc/</code> until you commit.</p>
    <form action="/training/preview" method="post" enctype="multipart/form-data" class="training-preview-form" id="training-preview-form" data-loading-form>
        <input type="hidden" name="session_id" value="{_esc(session.session_id)}">
        <div id="training-preview-selected-tuples"></div>
        <div class="training-preview-options">
            <input type="file" name="preview_file" class="file-input training-preview-file" accept=".json,.ndjson" required>
            <label class="filter-option">
                <input type="checkbox" name="bad_satisfaction_only" value="true"{checked}>
                Only preview tickets with bad CSAT rating
            </label>
            <button type="submit" class="btn btn-secondary" id="training-preview-btn" data-loading-btn data-loading-label="Running preview…" disabled>Run preview</button>
        </div>
    </form>
    """


def training_preview_section_html(
    session: _TrainingSession,
    selected: frozenset[tuple[str, str, str, str, str]],
    result: AllowlistCompareResult | None,
) -> str:
    if result is None and session.preview_result is None:
        return ""

    stale = preview_is_stale(session, selected) if session.preview_result else False
    display = result or session.preview_result
    body = compare_result_html(display, stale=stale) if display else ""
    stale_banner = ""
    if stale:
        stale_banner = (
            '<p class="training-stale-banner" role="status">'
            "Selection changed — re-run preview to update metrics.</p>"
        )
    return f"""
    <h2 class="section-header">Preview results</h2>
    {stale_banner}
    {body}
    """


def training_footer_html(*, show_revert: bool, show_back: bool = True) -> str:
    revert = ""
    if show_revert:
        revert = """
        <form action="/training/revert" method="post" class="training-revert-form">
            <button type="submit" class="btn btn-secondary">Undo last update</button>
        </form>
        <p class="meta">Restores the reference workbook and <code>training_rules.json</code> from the most recent Training commit snapshot (disk only — does not undo git history).</p>
        """
    back = ""
    if show_back:
        back = '<p class="links"><a href="/" class="btn btn-secondary">Back to classify</a></p>'
    return f"""
    <footer class="training-footer">
        {back}
        {revert}
    </footer>"""


def training_page_shell(*, title: str, head: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>{head}
<script src="/static/training.js" defer></script>
</head>
<body>
<div class="container training-page">
    <h1 class="page-header">{_esc(title)}</h1>
    {body}
</div>
</body></html>"""


def _esc(v: object) -> str:
    if v is None:
        return ""
    s = str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    return s
