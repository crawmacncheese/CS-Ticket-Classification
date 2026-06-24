"""Shared ticket preview table with progressive disclosure and detail pane."""

from __future__ import annotations

import json
from typing import Any

from cs_tickets.portal_copy import (
    SHOW_TICKET_PREVIEW_DETAILS_LABEL,
    SHOW_TICKET_PREVIEW_TBC_ONLY_LABEL,
    TICKET_PREVIEW_CAP_META,
    TICKET_PREVIEW_SELECT_HINT,
    TBC_REASON_EXPLANATIONS,
    TBC_REASON_LABELS,
)

_TIER_COLS = (
    "Tier1_Segment",
    "Tier2_Stream",
    "Tier3_Cat",
    "Tier4_Type",
    "Granular_Tech_UI_Type",
)


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


def _esc_detail(v: object) -> str:
    """Full escape for detail pane — no length cap."""
    return _esc(v)


def _truncate_cell(v: object, limit: int = 80) -> str:
    s = str(v) if v is not None else ""
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _format_tags(tags: object) -> str:
    if tags is None:
        return ""
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            if isinstance(parsed, list):
                return ", ".join(str(t) for t in parsed)
        except json.JSONDecodeError:
            pass
        return tags
    if isinstance(tags, list):
        return ", ".join(str(t) for t in tags)
    return str(tags)


def _tier_path_html(row: dict[str, Any]) -> str:
    parts = [_esc(row.get(c) or "") for c in _TIER_COLS[:4]]
    main = " &rarr; ".join(parts)
    granular = row.get("Granular_Tech_UI_Type") or ""
    if granular and granular != "N/A":
        return (
            f'<span class="category-path-main">{main}</span>'
            f'<span class="category-path-granular">{_esc(granular)}</span>'
        )
    return f'<span class="category-path-main">{main}</span>'


def _tuple_path_html(tup: tuple[str, ...] | list[str] | None) -> str:
    if not tup or len(tup) < 4:
        return ""
    parts = [_esc(v) for v in tup[:4]]
    main = " &rarr; ".join(parts)
    granular = tup[4] if len(tup) > 4 else ""
    if granular and granular != "N/A":
        return (
            f'<span class="category-path-main">{main}</span>'
            f'<span class="category-path-granular">{_esc(granular)}</span>'
        )
    return f'<span class="category-path-main">{main}</span>'


def _reason_badge(reason: str | None) -> str:
    if not reason or reason == "not_tbc":
        return ""
    label = TBC_REASON_LABELS.get(reason, reason)
    return (
        f'<span class="tbc-reason-badge" title="{_esc(reason)}">{_esc(label)}</span>'
    )


def _classify_preview_row_html(
    row: dict[str, Any],
    *,
    tbc_reason: str | None,
) -> str:
    reason = tbc_reason or "not_tbc"
    is_tbc = reason != "not_tbc"
    return (
        f'<tr class="ticket-preview-row" data-ticket-id="{_esc(row.get("id"))}" '
        f'data-tbc-reason="{_esc(reason)}" data-is-tbc="{str(is_tbc).lower()}">'
        f"<td>{_esc(row.get('id'))}</td>"
        f"<td class='preview-col-compact'>{_esc(_truncate_cell(row.get('subject'), 120))}</td>"
        f"<td class='preview-col-compact'>{_esc(row.get('Tier4_Type'))}</td>"
        f"<td class='preview-col-detail' hidden>{_esc(row.get('Tier1_Segment'))}</td>"
        f"<td class='preview-col-detail' hidden>{_esc(row.get('Tier2_Stream'))}</td>"
        f"<td class='preview-col-detail' hidden>{_esc(row.get('Tier3_Cat'))}</td>"
        f"<td class='preview-col-detail' hidden>{_esc(row.get('Granular_Tech_UI_Type'))}</td>"
        f"<td class='preview-col-detail' hidden>{_reason_badge(reason)}</td>"
        f"<td class='preview-col-detail' hidden>{_esc(_truncate_cell(_format_tags(row.get('tags'))))}</td>"
        f"<td class='preview-col-detail' hidden>{_esc(row.get('created_at'))}</td>"
        f"</tr>"
    )


def _changed_preview_row_html(ch: dict[str, Any]) -> str:
    old_reason = ch.get("old_tbc_reason") or ""
    new_reason = ch.get("new_tbc_reason") or ""
    is_tbc = bool(ch.get("old_tbc") or ch.get("new_tbc"))
    primary_reason = new_reason or old_reason or "not_tbc"
    return (
        f'<tr class="ticket-preview-row" data-ticket-id="{_esc(ch.get("id"))}" '
        f'data-tbc-reason="{_esc(primary_reason)}" data-is-tbc="{str(is_tbc).lower()}">'
        f"<td>{_esc(ch.get('id'))}</td>"
        f"<td class='preview-col-compact'>{_esc(ch.get('old_tier4'))}</td>"
        f"<td class='preview-col-compact'>{_esc(ch.get('new_tier4'))}</td>"
        f"<td class='preview-col-detail' hidden>{_esc(ch.get('outcome_type'))}</td>"
        f"<td class='preview-col-detail' hidden>{_esc(ch.get('gap_fix_mechanism'))}</td>"
        f"<td class='preview-col-detail' hidden>{_reason_badge(old_reason if ch.get('old_tbc') else None)}</td>"
        f"<td class='preview-col-detail' hidden>{_reason_badge(new_reason if ch.get('new_tbc') else None)}</td>"
        f"</tr>"
    )


def _classify_json_row(row: dict[str, Any], *, tbc_reason: str | None) -> dict[str, Any]:
    return {
        "id": str(row.get("id") or ""),
        "subject": row.get("subject"),
        "description": row.get("description"),
        "tags": row.get("tags"),
        "created_at": row.get("created_at"),
        "tier_path": [row.get(c) for c in _TIER_COLS],
        "tbc_reason": tbc_reason or "not_tbc",
        "is_tbc": (tbc_reason or "not_tbc") != "not_tbc",
    }


def _changed_json_row(ch: dict[str, Any]) -> dict[str, Any]:
    old_reason = ch.get("old_tbc_reason")
    new_reason = ch.get("new_tbc_reason")
    primary = new_reason or old_reason or "not_tbc"
    return {
        "id": str(ch.get("id") or ""),
        "subject": ch.get("subject"),
        "description": ch.get("description"),
        "tags": ch.get("tags"),
        "old_tier4": ch.get("old_tier4"),
        "new_tier4": ch.get("new_tier4"),
        "old_tuple": list(ch["old_tuple"]) if ch.get("old_tuple") else None,
        "new_tuple": list(ch["new_tuple"]) if ch.get("new_tuple") else None,
        "old_tbc_reason": old_reason,
        "new_tbc_reason": new_reason,
        "old_tbc": bool(ch.get("old_tbc")),
        "new_tbc": bool(ch.get("new_tbc")),
        "outcome_type": ch.get("outcome_type"),
        "gap_fix_mechanism": ch.get("gap_fix_mechanism"),
        "tbc_reason": primary,
        "is_tbc": bool(ch.get("old_tbc") or ch.get("new_tbc")),
        "mode": "changed",
    }


def ticket_preview_html(
    tickets: list[dict],
    *,
    tbc_reasons: dict[str, str] | None = None,
    limit: int = 200,
    table_id: str = "classify-ticket-preview",
    mode: str = "classify",
) -> str:
    """Render compact ticket preview with disclosure controls and embedded JSON."""
    if not tickets:
        return '<p class="meta">No tickets to preview.</p>'

    slice_rows = tickets[:limit]
    data_id = f"{table_id}-data"
    tbc_reasons = tbc_reasons or {}

    if mode == "changed":
        rows_html = "".join(_changed_preview_row_html(ch) for ch in slice_rows)
        json_rows = [_changed_json_row(ch) for ch in slice_rows]
        thead = (
            "<thead><tr>"
            "<th>Ticket id</th>"
            "<th>Old category</th>"
            "<th>New category</th>"
            "<th class='preview-col-detail' hidden>Outcome</th>"
            "<th class='preview-col-detail' hidden>Mechanism</th>"
            "<th class='preview-col-detail' hidden>Old TBC reason</th>"
            "<th class='preview-col-detail' hidden>New TBC reason</th>"
            "</tr></thead>"
        )
    else:
        rows_html = "".join(
            _classify_preview_row_html(
                row,
                tbc_reason=tbc_reasons.get(str(row.get("id") or "")),
            )
            for row in slice_rows
        )
        json_rows = [
            _classify_json_row(
                row,
                tbc_reason=tbc_reasons.get(str(row.get("id") or "")),
            )
            for row in slice_rows
        ]
        thead = (
            "<thead><tr>"
            "<th>Ticket id</th>"
            "<th>Subject</th>"
            "<th>Category (Tier 4)</th>"
            "<th class='preview-col-detail' hidden>Tier 1</th>"
            "<th class='preview-col-detail' hidden>Tier 2</th>"
            "<th class='preview-col-detail' hidden>Tier 3</th>"
            "<th class='preview-col-detail' hidden>Granular</th>"
            "<th class='preview-col-detail' hidden>TBC reason</th>"
            "<th class='preview-col-detail' hidden>Tags</th>"
            "<th class='preview-col-detail' hidden>Created</th>"
            "</tr></thead>"
        )

    tbc_in_slice = sum(1 for r in json_rows if r.get("is_tbc"))
    cap_meta = TICKET_PREVIEW_CAP_META.format(shown=len(slice_rows), limit=limit)
    more = ""
    if len(tickets) > limit:
        more = f'<p class="meta">Export has {len(tickets)} rows; preview shows first {limit}.</p>'

    json_blob = json.dumps(
        {
            "mode": mode,
            "limit": limit,
            "rows": json_rows,
            "labels": TBC_REASON_LABELS,
            "explanations": TBC_REASON_EXPLANATIONS,
            "select_hint": TICKET_PREVIEW_SELECT_HINT,
        },
        ensure_ascii=False,
    )

    return f"""
<div class="ticket-preview-root" data-mode="{_esc(mode)}" data-table-id="{_esc(table_id)}">
  <div class="ticket-preview-controls">
    <label class="filter-option ticket-preview-toggle">
      <input type="checkbox" id="show-ticket-preview-tbc-only" class="show-ticket-preview-tbc-only">
      {SHOW_TICKET_PREVIEW_TBC_ONLY_LABEL}
    </label>
    <label class="filter-option ticket-preview-toggle">
      <input type="checkbox" id="show-ticket-preview-details" class="show-ticket-preview-details">
      {SHOW_TICKET_PREVIEW_DETAILS_LABEL}
    </label>
  </div>
  <p class="meta ticket-preview-cap-meta">{_esc(cap_meta)}</p>
  <p class="meta ticket-preview-tbc-meta" hidden data-tbc-in-slice="{tbc_in_slice}"></p>
  <div class="preview-wrap">
    <table class="preview-table ticket-preview-table" id="{_esc(table_id)}">
      {thead}
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div id="ticket-preview-detail" class="ticket-preview-detail" aria-live="polite">
    <p class="ticket-preview-detail-placeholder meta">{TICKET_PREVIEW_SELECT_HINT}</p>
    <div class="ticket-preview-detail-content" hidden></div>
  </div>
  {more}
  <script type="application/json" id="{_esc(data_id)}">{json_blob}</script>
</div>""".strip()
