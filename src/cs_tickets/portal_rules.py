"""Portal UI and helpers for conversational rule authoring."""

from __future__ import annotations

import json
from typing import Any

from cs_tickets.classifier_rules import RuleSpec, _rule_from_dict, rule_spec_to_json
from cs_tickets.classify import classify_row_with_explanation
from cs_tickets.portal_classify_context import build_tbc_rule_prefill
from cs_tickets.taxonomy import AllowList


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def rule_tier_path(rule: RuleSpec) -> str:
    return " → ".join(rule.tier[:4])


def rule_matchers_summary(rule: RuleSpec) -> str:
    parts: list[str] = []
    if rule.any_requester_domain:
        parts.append(f"domain: {', '.join(rule.any_requester_domain)}")
    if rule.any_requester:
        parts.append(f"requester: {', '.join(rule.any_requester)}")
    if rule.any_subject:
        parts.append(f"subject: {', '.join(rule.any_subject)}")
    if rule.any_blob:
        parts.append(f"text: {', '.join(rule.any_blob)}")
    if rule.any_tags:
        parts.append(f"tags: {', '.join(rule.any_tags)}")
    if rule.exclude_blob:
        parts.append(f"exclude: {', '.join(rule.exclude_blob)}")
    return "; ".join(parts) or "—"


def filter_rules(
    rules: tuple[RuleSpec, ...],
    *,
    q: str = "",
    tier1: str = "",
    tier2: str = "",
    tier3: str = "",
    tier4: str = "",
    status: str = "",
    override: str = "",
) -> tuple[RuleSpec, ...]:
    """Filter rules for the /rules UI (case-insensitive)."""

    def norm(v: object) -> str:
        return str(v or "").strip().lower()

    qn = norm(q)
    t1 = norm(tier1)
    t2 = norm(tier2)
    t3 = norm(tier3)
    t4 = norm(tier4)
    st = norm(status)
    ov = norm(override)

    out: list[RuleSpec] = []
    for rule in rules:
        if st:
            if st == "active" and not rule.enabled:
                continue
            if st == "disabled" and rule.enabled:
                continue
        if ov:
            want = ov in ("1", "true", "yes", "y", "override")
            if bool(rule.override) != want:
                continue
        if t1 and norm(rule.tier[0]) != t1:
            continue
        if t2 and norm(rule.tier[1]) != t2:
            continue
        if t3 and norm(rule.tier[2]) != t3:
            continue
        if t4 and norm(rule.tier[3]) != t4:
            continue

        if qn:
            hay = " | ".join(
                [
                    rule.id,
                    rule.display_name or "",
                    rule_tier_path(rule),
                    rule_matchers_summary(rule),
                ]
            ).lower()
            if qn not in hay:
                continue
        out.append(rule)
    return tuple(out)


def rules_filter_bar_html(
    *,
    q: str = "",
    tier1: str = "",
    tier2: str = "",
    tier3: str = "",
    tier4: str = "",
    status: str = "",
    override: str = "",
    total: int,
    shown: int,
) -> str:
    status = status.lower().strip()
    override = override.lower().strip()
    status_opt = lambda v: "selected" if status == v else ""
    override_opt = lambda v: "selected" if override == v else ""
    meta = f"Showing <strong>{shown}</strong> of <strong>{total}</strong> rules."
    return f"""
    <form class="tbc-filter-bar rules-filter-bar" method="get" action="/rules">
      <div class="tbc-filter-nl-row">
        <label class="tbc-filter-field tbc-filter-field--grow">
          <span class="tbc-filter-label">Search focus (natural language)</span>
          <input type="text" id="rules-filter-nl" class="tbc-filter-input"
            placeholder="e.g. review B2C cancellation; stripe payment completed"
            autocomplete="off" />
        </label>
        <button type="button" class="btn btn-secondary btn-sm" id="rules-filter-nl-apply">Apply focus</button>
      </div>
      <p id="rules-filter-nl-status" class="meta tbc-filter-nl-status" hidden aria-live="polite"></p>
      <label class="tbc-filter-field tbc-filter-field--grow">
        <span class="tbc-filter-label">Search</span>
        <input type="search" name="q" class="tbc-filter-input"
          placeholder="id, match text, category…" value="{_esc(q)}" autocomplete="off" />
      </label>
      <label class="tbc-filter-field">
        <span class="tbc-filter-label">Tier1</span>
        <input type="text" name="tier1" class="tbc-filter-input" value="{_esc(tier1)}" placeholder="B2C/B2B" />
      </label>
      <label class="tbc-filter-field">
        <span class="tbc-filter-label">Tier4</span>
        <input type="text" name="tier4" class="tbc-filter-input" value="{_esc(tier4)}" placeholder="e.g. System Report" />
      </label>
      <label class="tbc-filter-field">
        <span class="tbc-filter-label">Status</span>
        <select name="status" class="tbc-filter-select">
          <option value="" {status_opt("")}>All</option>
          <option value="active" {status_opt("active")}>Active</option>
          <option value="disabled" {status_opt("disabled")}>Disabled</option>
        </select>
      </label>
      <label class="tbc-filter-field">
        <span class="tbc-filter-label">Override</span>
        <select name="override" class="tbc-filter-select">
          <option value="" {override_opt("")}>All</option>
          <option value="true" {override_opt("true")}>Yes</option>
          <option value="false" {override_opt("false")}>No</option>
        </select>
      </label>
      <button type="submit" class="btn btn-secondary btn-sm">Apply</button>
      <a class="btn btn-secondary btn-sm" href="/rules">Clear</a>
      <p class="meta" style="margin: 8px 0 0 0;">{meta}</p>
      <input type="hidden" name="tier2" value="{_esc(tier2)}" />
      <input type="hidden" name="tier3" value="{_esc(tier3)}" />
    </form>
    """.strip()


def build_rule_prefill(
    *,
    ticket_id: str,
    subject: str,
    suggested_tier: str,
    why_tbc: str,
    explain_evidence: str,
    row: dict | None = None,
    explain: dict | None = None,
) -> str:
    if row is not None and explain is not None:
        return build_tbc_rule_prefill(
            ticket_id=ticket_id,
            row=row,
            explain=explain,
        )
    snippet = (subject or "")[:80]
    return build_tbc_rule_prefill(
        ticket_id=ticket_id,
        row={"subject": snippet, "description": ""},
        explain={
            "fallback_used": True,
            "why_tbc": why_tbc,
            "tbc_reason_detail": why_tbc,
            "evidence": [{"rule_id": explain_evidence}] if explain_evidence else [],
            "candidates": [],
            "tier": [],
        },
    )


def rules_list_html(
    rules: tuple[RuleSpec, ...],
    *,
    config_version: int,
    can_confirm: bool = True,
) -> str:
    rows: list[str] = []
    for rule in sorted(rules, key=lambda r: r.id):
        status = "disabled" if not rule.enabled else "active"
        label = rule.display_name or rule.id
        rows.append(
            f"<tr class=\"rules-row-{status}\">"
            f"<td><code>{_esc(rule.id)}</code>"
            f"{f'<br><span class=\"meta\">{_esc(rule.display_name)}</span>' if rule.display_name else ''}</td>"
            f"<td class=\"category-path-cell\">{_esc(rule_tier_path(rule))}</td>"
            f"<td>{_esc(rule_matchers_summary(rule))}</td>"
            f"<td>{'yes' if rule.override else '—'}</td>"
            f"<td>{status}</td>"
            f"<td>"
            f"<a class=\"btn btn-secondary btn-sm\" href=\"/rules/new?rule_id={_esc(rule.id)}\">Edit</a> "
            + (
                f"<form class=\"rules-inline-form\" method=\"post\" action=\"/rules/disable\" "
                f"data-confirm-lead=\"Disable rule {_esc(rule.id)}?\">"
                f"<input type=\"hidden\" name=\"rule_id\" value=\"{_esc(rule.id)}\">"
                f"<button type=\"submit\" class=\"btn btn-secondary btn-sm\">Disable</button></form>"
                if rule.enabled and can_confirm
                else ""
            )
            + "</td></tr>"
        )
    body = "\n".join(rows) or "<tr><td colspan=\"6\" class=\"meta\">No rules in live config.</td></tr>"
    return f"""
    <p class="meta">Live config version <strong>{config_version}</strong>.</p>
    <table class="stats-table rules-list-table">
      <thead><tr>
        <th>Rule</th><th>Category</th><th>Match</th><th>Override</th><th>Status</th><th></th>
      </tr></thead>
      <tbody>{body}</tbody>
    </table>
    """


def rules_editor_html(
    *,
    prefill: str = "",
    run_id: str = "",
    ticket_id: str = "",
    initial_rule: RuleSpec | None = None,
    can_confirm: bool = True,
) -> str:
    initial_json = json.dumps(rule_spec_to_json(initial_rule)) if initial_rule else "null"
    # Always include run/ticket inputs so preview can work even when the page
    # is opened without context (rules list → edit). JS can auto-fill run_id
    # from the last viewed run via sessionStorage.
    run_id_value = _esc(run_id)
    ticket_id_value = _esc(ticket_id)
    context_panel = f"""
      <details class="rules-context" {"open" if not run_id_value else ""}>
        <summary>Optional run context</summary>
        <div class="tbc-filter-bar rules-context-bar">
          <label class="tbc-filter-field">
            <span class="tbc-filter-label">Run ID</span>
            <input type="text" id="rules-run-id" class="tbc-filter-input" value="{run_id_value}"
              placeholder="Used for linking back to a run after Confirm" autocomplete="off" />
          </label>
          <label class="tbc-filter-field">
            <span class="tbc-filter-label">Ticket ID</span>
            <input type="text" id="rules-ticket-id" class="tbc-filter-input" value="{ticket_id_value}"
              placeholder="Optional; used for rule authoring context only" autocomplete="off" />
          </label>
          <p class="meta" style="margin: 6px 0 0 0;">
            Preview uses the <strong>uploaded export</strong> below (not a run).
          </p>
        </div>
      </details>
    """.strip()
    prefill_esc = _esc(prefill)
    confirm_attrs = "" if can_confirm else ' hidden data-requires-lead="1"'
    lead_note = (
        ""
        if can_confirm
        else '<p class="meta rules-lead-note">Compiled rules need a team lead to confirm live.</p>'
    )
    return f"""
    <script type="application/json" id="rules-initial-rule">{initial_json}</script>
    <div id="rules-app" class="rules-app" data-can-confirm="{"true" if can_confirm else "false"}">
      {context_panel}
      {lead_note}
      <div class="rules-chat-panel">
        <div id="rules-chat-log" class="rules-chat-log" aria-live="polite"></div>
        <form id="rules-chat-form" class="rules-chat-form">
          <label class="sr-only" for="rules-chat-input">Describe a routing rule</label>
          <textarea id="rules-chat-input" class="rules-chat-input" rows="3"
            placeholder="e.g. Map &quot;Stripe payment completed&quot; to Billing System Report">{prefill_esc}</textarea>
          <button type="submit" class="btn btn-primary" id="rules-send-btn">Compile</button>
        </form>
      </div>
      <div id="rules-review-panel" class="rules-review-panel" hidden>
        <h2 class="rules-review-heading">Compiled rule (review before Confirm)</h2>
        <div id="rules-review-summary" class="rules-review-summary"></div>
        <details class="rules-advanced-edit">
          <summary>Advanced edit (JSON)</summary>
          <textarea id="rules-advanced-json" class="rules-advanced-json" rows="12"></textarea>
        </details>
        <div class="rules-review-actions">
          <div class="rules-upload-preview">
            <label class="meta rules-upload-label">
              Optional: upload an export file to preview against it
            </label>
            <input
              type="file"
              id="rules-upload-preview-file"
              accept=".json,.ndjson"
              class="rules-upload-input"
            />
            <button type="button" class="btn btn-secondary btn-sm" id="rules-preview-upload-btn" disabled>
              Preview on uploaded file
            </button>
          </div>
          <button type="button" class="btn btn-primary" id="rules-confirm-btn" disabled{confirm_attrs}>Confirm live</button>
        </div>
        <div id="rules-preview-results" class="rules-preview-results" hidden></div>
      </div>
    </div>
    """


def preview_rule_on_rows(
    rows: list[dict[str, Any]],
    allow: AllowList,
    live_rules: tuple[RuleSpec, ...],
    candidate: RuleSpec,
    *,
    ticket_ids: tuple[str, ...] = (),
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Sandbox classify with live rules + candidate."""
    specs = live_rules + (candidate,)
    selected = ticket_ids
    out: list[dict[str, Any]] = []
    for row in rows:
        tid = str(row.get("id") or "")
        if selected and tid not in selected:
            continue
        before = classify_row_with_explanation(row, allow, rule_specs=live_rules)
        after = classify_row_with_explanation(row, allow, rule_specs=specs)
        if before.tier != after.tier or not selected:
            if before.tier != after.tier or tid in selected:
                out.append(
                    {
                        "ticket_id": tid,
                        "subject": row.get("subject") or "",
                        "before": list(before.tier),
                        "after": list(after.tier),
                        "matched": candidate.id in {ev.rule_id for ev in after.evidence},
                    }
                )
        if len(out) >= limit:
            break
    if not out and rows:
        row = rows[0]
        after = classify_row_with_explanation(row, allow, rule_specs=specs)
        out.append(
            {
                "ticket_id": str(row.get("id") or ""),
                "subject": row.get("subject") or "",
                "before": list(classify_row_with_explanation(row, allow, rule_specs=live_rules).tier),
                "after": list(after.tier),
                "matched": candidate.id in {ev.rule_id for ev in after.evidence},
            }
        )
    return out


def parse_rule_json(raw: dict[str, Any]) -> RuleSpec:
    return _rule_from_dict(raw)
