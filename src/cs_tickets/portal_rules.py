"""Portal UI and helpers for conversational rule authoring."""

from __future__ import annotations

import json
from typing import Any

from cs_tickets.classifier_rules import RuleSpec, _rule_from_dict, rule_spec_to_json
from cs_tickets.classify import ClassificationDecision, classify_row_with_explanation
from cs_tickets.portal_classify_context import build_tbc_rule_prefill
from cs_tickets.portal_copy import (
    RULES_CONFIRM_BUTTON,
    RULES_DOCK_TAB_CHAT,
    RULES_DOCK_TAB_RULE,
    RULES_REVIEW_EMPTY,
    RULES_REVIEW_HEADING,
)
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
      <label class="tbc-filter-field tbc-filter-field--grow">
        <span class="tbc-filter-label">Search</span>
        <input type="search" name="q" class="tbc-filter-input"
          placeholder="id, match text, category…" value="{_esc(q)}" autocomplete="off" />
      </label>
      <label class="tbc-filter-field">
        <span class="tbc-filter-label">Segment</span>
        <input type="text" name="tier1" class="tbc-filter-input" value="{_esc(tier1)}" placeholder="B2C/B2B" />
      </label>
      <label class="tbc-filter-field">
        <span class="tbc-filter-label">Category</span>
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
            f"<td class=\"rules-list-actions-col\">"
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
    <div class="rules-list-scroll">
      <table class="stats-table rules-list-table">
        <thead><tr>
          <th>Rule</th><th>Category</th><th>Match</th><th>Override</th><th>Status</th>
          <th class="rules-list-actions-col">Actions</th>
        </tr></thead>
        <tbody>{body}</tbody>
      </table>
    </div>
    """


def rules_editor_html(
    *,
    prefill: str = "",
    run_id: str = "",
    ticket_id: str = "",
    initial_rule: RuleSpec | None = None,
    can_confirm: bool = True,
    orchestration: bool = False,
    dock: bool = False,
    split: bool = False,
    return_to: str = "",
) -> str:
    initial_json = json.dumps(rule_spec_to_json(initial_rule)) if initial_rule else "null"
    # Always include run/ticket inputs so preview can work even when the page
    # is opened without context (rules list → edit). JS can auto-fill run_id
    # from the last viewed run via sessionStorage.
    run_id_value = _esc(run_id)
    ticket_id_value = _esc(ticket_id)
    orch = bool(orchestration or run_id)
    mode_label = "Config" if initial_rule else ("Audit" if orch else "Config")
    badge = (
        f'<span id="rules-orch-badge" class="rules-orch-badge" data-mode="{_esc(mode_label.lower())}">'
        f"{_esc(mode_label)}</span>"
        if orch
        else ""
    )
    context_open = ""
    if not dock and not run_id_value:
        context_open = " open"
    context_panel = f"""
      <details class="rules-context"{context_open}>
        <summary>Optional run context</summary>
        <div class="tbc-filter-bar rules-context-bar">
          <label class="tbc-filter-field">
            <span class="tbc-filter-label">Run ID</span>
            <input type="text" id="rules-run-id" class="tbc-filter-input" value="{run_id_value}"
              placeholder="Used for profile, preview, and reclassify after Confirm" autocomplete="off" />
          </label>
          <label class="tbc-filter-field">
            <span class="tbc-filter-label">Ticket ID</span>
            <input type="text" id="rules-ticket-id" class="tbc-filter-input" value="{ticket_id_value}"
              placeholder="Optional; used for rule authoring context only" autocomplete="off" />
          </label>
          <p class="meta rules-context-help">
            With a run id, preview uses the live run rows. Upload preview remains as a fallback.
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
    placeholder = (
        "e.g. review B2C — or show all TBC — or Map \"…\" to System Report"
        if orch
        else 'e.g. Map &quot;Stripe payment completed&quot; to Billing System Report'
    )
    send_label = "Send" if orch else "Compile"
    orch_hint = ""
    if orch and not dock:
        orch_hint = (
            '<p class="meta rules-orch-hint">Orchestration mode: profile (“review B2C”), '
            "open TBC (“show all TBC”), or draft a rule with a Map/compile phrase — "
            "unclear asks will clarify instead of inventing a rule.</p>"
        )
    # Dock: skip long hint — badge alone is enough; keep chat input above the fold.
    # In the side dock, run_id is fixed; hide optional context to save space.
    if dock and run_id_value:
        context_panel = (
            f'<input type="hidden" id="rules-run-id" value="{run_id_value}" />'
            f'<input type="hidden" id="rules-ticket-id" value="{ticket_id_value}" />'
        )
    chat_rows = "2" if dock else "3"
    advanced_rows = "8" if dock else "12"
    upload_block = ""
    if not dock:
        upload_block = """
          <div class="rules-upload-preview" id="rules-upload-preview-wrap">
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
          </div>"""
    else:
        # Keep ids so rules.js optional upload handlers stay no-ops when missing.
        upload_block = (
            '<div class="rules-upload-preview" id="rules-upload-preview-wrap" hidden>'
            '<input type="file" id="rules-upload-preview-file" accept=".json,.ndjson" />'
            '<button type="button" id="rules-preview-upload-btn" hidden disabled></button>'
            "</div>"
        )
    dock_cls = " rules-app--dock" if dock else ""
    split_cls = " rules-app--split" if split else ""
    return_to_attr = f' data-return-to="{_esc(return_to)}"' if return_to else ""
    review_panel_hidden = "" if split else " hidden"
    review_empty = (
        f'<p id="rules-review-empty" class="rules-review-empty meta">{_esc(RULES_REVIEW_EMPTY)}</p>'
        if split
        else ""
    )
    review_body_attrs = ' id="rules-review-body"' + (" hidden" if split else "")

    def _review_panel(*, panel_hidden: str, empty_html: str, body_attrs: str, extra_cls: str = "") -> str:
        cls = f"rules-review-panel{extra_cls}{panel_hidden}"
        return f"""
      <div id="rules-review-panel" class="{cls.strip()}">
        <h2 class="rules-review-heading">{_esc(RULES_REVIEW_HEADING)}</h2>
        {empty_html}
        <div{body_attrs}>
          <div id="rules-review-summary" class="rules-review-summary"></div>
          <details class="rules-advanced-edit">
            <summary>Advanced edit (JSON)</summary>
            <textarea id="rules-advanced-json" class="rules-advanced-json" rows="{advanced_rows}"></textarea>
          </details>
          <div class="rules-review-actions">
            {upload_block}
            <button type="button" class="btn btn-primary" id="rules-confirm-btn" disabled{confirm_attrs}>{_esc(RULES_CONFIRM_BUTTON)}</button>
          </div>
          <div id="rules-preview-results" class="rules-preview-results" hidden></div>
        </div>
      </div>""".strip()

    review_panel_stack = _review_panel(
        panel_hidden=" hidden",
        empty_html="",
        body_attrs="",
    )
    review_panel_split = _review_panel(
        panel_hidden="",
        empty_html=review_empty,
        body_attrs=review_body_attrs,
    )
    review_panel_dock = _review_panel(
        panel_hidden="",
        empty_html="",
        body_attrs="",
        extra_cls=" rules-review-panel--dock-tab",
    )

    chat_panel = f"""
      <div class="rules-chat-panel">
        <div id="rules-chat-log" class="rules-chat-log" aria-live="polite"></div>
        <div id="rules-exec-log" class="rules-exec-log meta" hidden></div>
        <form id="rules-chat-form" class="rules-chat-form">
          <label class="sr-only" for="rules-chat-input">Describe a routing rule or review focus</label>
          <textarea id="rules-chat-input" class="rules-chat-input" rows="{chat_rows}"
            placeholder="{placeholder}">{prefill_esc}</textarea>
          <button type="submit" class="btn btn-primary" id="rules-send-btn">{send_label}</button>
        </form>
      </div>""".strip()

    if dock:
        main_panels = f"""
      <div class="rules-dock-tabs" id="rules-dock-tabs" role="tablist" aria-label="Review chat views">
        <button type="button" class="rules-dock-tab is-active" id="rules-dock-tab-chat"
          data-rules-tab="chat" role="tab" aria-selected="true" aria-controls="rules-dock-panel-chat">{_esc(RULES_DOCK_TAB_CHAT)}</button>
        <button type="button" class="rules-dock-tab" id="rules-dock-tab-rule"
          data-rules-tab="rule" role="tab" aria-selected="false" aria-controls="rules-dock-panel-rule" hidden>{_esc(RULES_DOCK_TAB_RULE)}</button>
      </div>
      <div class="rules-dock-panels">
        <div class="rules-dock-panel" id="rules-dock-panel-chat" data-rules-panel="chat" role="tabpanel">
          {chat_panel}
        </div>
        <div class="rules-dock-panel" id="rules-dock-panel-rule" data-rules-panel="rule" role="tabpanel" hidden>
          {review_panel_dock}
        </div>
      </div>"""
    elif split:
        main_panels = f"""
      <div class="rules-split-layout">
        {chat_panel}
        {review_panel_split}
      </div>"""
    else:
        main_panels = f"""
      {chat_panel}
      {review_panel_stack}"""

    return f"""
    <script type="application/json" id="rules-initial-rule">{initial_json}</script>
    <div id="rules-app" class="rules-app{dock_cls}{split_cls}"
      data-can-confirm="{"true" if can_confirm else "false"}"
      data-orchestration="{"true" if orch else "false"}"
      data-preview-ok="false"
      data-dock="{"true" if dock else "false"}"
      data-split="{"true" if split else "false"}"{return_to_attr}>
      <div class="rules-orch-header">
        {badge}
        {orch_hint}
      </div>
      {context_panel}
      {lead_note}
      {main_panels}
    </div>
    """


def _evidence_payload(decision: ClassificationDecision) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": ev.rule_id,
            "weight": ev.weight,
            "signal": ev.signal,
            "tier": list(ev.tier),
        }
        for ev in decision.evidence
    ]


def _rule_ids(decision: ClassificationDecision) -> set[str]:
    return {ev.rule_id for ev in decision.evidence}


def summarize_preview_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate preview rows for cards: changed / matched / shield overlap counts."""
    changed = 0
    matched = 0
    won = 0
    shield_overlap = 0
    shield_rule_counts: dict[str, int] = {}
    for row in results:
        if row.get("tier_changed"):
            changed += 1
        if row.get("candidate_matched") or row.get("matched"):
            matched += 1
        if row.get("candidate_won"):
            won += 1
        overlaps = row.get("shield_overlap") or []
        if overlaps:
            shield_overlap += 1
            for rid in overlaps:
                key = str(rid)
                shield_rule_counts[key] = shield_rule_counts.get(key, 0) + 1
    return {
        "result_rows": len(results),
        "changed": changed,
        "candidate_matched": matched,
        "candidate_won": won,
        "shield_overlap": shield_overlap,
        "shield_overlap_rules": shield_rule_counts,
        "headline": (
            f"{changed} changed; {matched} matched; {shield_overlap} overlap"
            + (
                " "
                + ", ".join(f"{n} {rid}" for rid, n in sorted(shield_rule_counts.items())[:3])
                if shield_rule_counts
                else ""
            )
        ),
    }


def _preview_row_detail_fields(row: dict[str, Any]) -> dict[str, Any]:
    tags = row.get("tags")
    if isinstance(tags, list):
        tags_s = ", ".join(str(t) for t in tags)
    elif tags is None:
        tags_s = ""
    else:
        tags_s = str(tags)
    return {
        "requester_email": str(row.get("requester_email") or ""),
        "tags": tags_s,
        "description": str(row.get("description") or ""),
    }


def preview_rule_on_rows(
    rows: list[dict[str, Any]],
    allow: AllowList,
    live_rules: tuple[RuleSpec, ...],
    candidate: RuleSpec,
    *,
    ticket_ids: tuple[str, ...] = (),
    limit: int = 50,
    scan_cap: int = 2000,
) -> list[dict[str, Any]]:
    """Sandbox classify with live rules + candidate.

    Each result includes overlap fields:
    ``evidence_before``, ``evidence_after``, ``candidate_matched``, ``candidate_won``,
    ``shield_overlap``, ``tier_changed`` (plus legacy ``matched`` / ``before`` / ``after``).
    """
    specs = live_rules + (candidate,)
    selected = frozenset(ticket_ids)
    shield_ids = {r.id for r in live_rules if r.override}
    out: list[dict[str, Any]] = []
    scanned = 0

    for row in rows:
        if scanned >= scan_cap:
            break
        tid = str(row.get("id") or "")
        if selected and tid not in selected:
            continue
        scanned += 1

        before = classify_row_with_explanation(row, allow, rule_specs=live_rules)
        after = classify_row_with_explanation(row, allow, rule_specs=specs)
        before_ids = _rule_ids(before)
        after_ids = _rule_ids(after)
        candidate_matched = candidate.id in after_ids
        tier_changed = before.tier != after.tier
        candidate_won = bool(candidate_matched and tier_changed)
        # Shields that fire on this ticket alongside candidate involvement
        if candidate_matched or tier_changed:
            shield_overlap = sorted(shield_ids & (before_ids | after_ids))
        else:
            shield_overlap = []

        interesting = (
            bool(selected)
            or tier_changed
            or candidate_matched
            or bool(shield_overlap and candidate_matched)
        )
        if not interesting:
            continue

        detail = _preview_row_detail_fields(row)
        out.append(
            {
                "ticket_id": tid,
                "subject": row.get("subject") or "",
                **detail,
                "before": list(before.tier),
                "after": list(after.tier),
                "matched": candidate_matched,  # legacy alias
                "candidate_matched": candidate_matched,
                "candidate_won": candidate_won,
                "tier_changed": tier_changed,
                "evidence_before": _evidence_payload(before),
                "evidence_after": _evidence_payload(after),
                "shield_overlap": shield_overlap,
            }
        )
        if len(out) >= limit:
            break

    if not out and rows:
        # Preserve previous “show something” behavior when nothing interesting found.
        row = rows[0]
        after = classify_row_with_explanation(row, allow, rule_specs=specs)
        before = classify_row_with_explanation(row, allow, rule_specs=live_rules)
        before_ids = _rule_ids(before)
        after_ids = _rule_ids(after)
        candidate_matched = candidate.id in after_ids
        tier_changed = before.tier != after.tier
        detail = _preview_row_detail_fields(row)
        out.append(
            {
                "ticket_id": str(row.get("id") or ""),
                "subject": row.get("subject") or "",
                **detail,
                "before": list(before.tier),
                "after": list(after.tier),
                "matched": candidate_matched,
                "candidate_matched": candidate_matched,
                "candidate_won": bool(candidate_matched and tier_changed),
                "tier_changed": tier_changed,
                "evidence_before": _evidence_payload(before),
                "evidence_after": _evidence_payload(after),
                "shield_overlap": sorted(shield_ids & (before_ids | after_ids))
                if candidate_matched
                else [],
            }
        )
    return out


def parse_rule_json(raw: dict[str, Any]) -> RuleSpec:
    return _rule_from_dict(raw)
