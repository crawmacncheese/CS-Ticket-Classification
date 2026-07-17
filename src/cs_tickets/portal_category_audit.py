"""Category audit page — Christine-style classified bucket review."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from cs_tickets.category_audit_filters import CategoryAuditFilter, filter_category_audit_rows
from cs_tickets.portal_copy import (
    CATEGORY_AUDIT_CHUNK_META,
    CATEGORY_AUDIT_CHUNK_NEXT,
    CATEGORY_AUDIT_CHUNK_PREV,
    CATEGORY_AUDIT_INCLUDE_TBC_LABEL,
    CATEGORY_AUDIT_PAGE_INTRO,
    CATEGORY_AUDIT_PAGE_TITLE,
    CATEGORY_AUDIT_PREVIEW_LINK,
    CATEGORY_AUDIT_RESULTS_LINK,
    CATEGORY_AUDIT_SLICE_EMPTY,
    CATEGORY_AUDIT_SLICE_EMPTY_ALL_TBC,
    CATEGORY_AUDIT_SWEEPS_HEADING,
    CATEGORY_AUDIT_SWEEPS_META,
    CATEGORY_AUDIT_TICKETS_HEADING,
    CATEGORY_FILTER_LABEL,
)
from cs_tickets.schema import TIER_COLUMNS

DEFAULT_CHUNK_SIZE = 10


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


def _embed_json_for_script(data: object) -> str:
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _tier_path_label(row: dict[str, Any]) -> str:
    return " → ".join(str(row.get(col) or "") for col in TIER_COLUMNS[:4])


def _parse_tags_list(tags: object) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(t) for t in tags]
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except json.JSONDecodeError:
            pass
        return [tags] if tags else []
    return [str(tags)]


def _ticket_cards_html(
    chunk_rows: list[dict[str, Any]],
    *,
    run_id: str,
    empty_message: str = CATEGORY_AUDIT_SLICE_EMPTY,
) -> str:
    if not chunk_rows:
        return f'<p class="meta">{_esc(empty_message)}</p>'
    cards: list[str] = []
    for row in chunk_rows:
        tid = str(row.get("id") or "")
        tags = ", ".join(_parse_tags_list(row.get("tags")))
        requester = str(row.get("requester_email") or "").strip()
        cards.append(
            f"""
<article class="category-audit-card" data-ticket-id="{_esc(tid)}">
  <header class="category-audit-card-header">
    <strong class="category-audit-card-id">#{_esc(tid)}</strong>
    <span class="category-audit-card-subject">{_esc(row.get("subject"))}</span>
  </header>
  <p class="meta category-audit-card-tier">{_esc(_tier_path_label(row))}</p>
  {f'<p class="meta category-audit-card-requester">Requester: {_esc(requester)}</p>' if requester else ""}
  <details class="category-audit-card-body">
    <summary>Full content</summary>
    <div class="category-audit-card-description">{_esc(row.get("description"))}</div>
    {f'<p class="meta category-audit-card-tags">Tags: {_esc(tags)}</p>' if tags else ""}
  </details>
  <p class="category-audit-card-actions">
    <button type="button" class="btn btn-secondary btn-sm category-audit-explain-btn"
      data-ticket-id="{_esc(tid)}">Explain</button>
    <button type="button" class="btn btn-secondary btn-sm category-audit-propose-rule-btn"
      data-ticket-id="{_esc(tid)}">Propose rule</button>
  </p>
  <div class="category-audit-explain-panel meta" hidden></div>
</article>
""".strip()
        )
    return '<div class="category-audit-cards">' + "\n".join(cards) + "</div>"


def _pagination_html(
    *,
    run_id: str,
    filt: CategoryAuditFilter,
    offset: int,
    limit: int,
    total_in_slice: int,
) -> str:
    if total_in_slice <= limit:
        return ""
    qs_base = filt.to_query_string()
    prev_off = max(0, offset - limit)
    next_off = offset + limit
    prev_qs = urlencode({"offset": prev_off, "limit": limit})
    next_qs = urlencode({"offset": next_off, "limit": limit})
    if qs_base:
        prev_href = f"/run/{_esc(run_id)}/category_audit?{qs_base}&{prev_qs}"
        next_href = f"/run/{_esc(run_id)}/category_audit?{qs_base}&{next_qs}"
    else:
        prev_href = f"/run/{_esc(run_id)}/category_audit?{prev_qs}"
        next_href = f"/run/{_esc(run_id)}/category_audit?{next_qs}"
    start = offset + 1 if total_in_slice else 0
    end = min(offset + limit, total_in_slice)
    meta = CATEGORY_AUDIT_CHUNK_META.format(start=start, end=end, total=total_in_slice)
    prev_btn = ""
    if offset > 0:
        prev_btn = (
            f'<a href="{prev_href}" class="btn btn-secondary btn-sm">'
            f"{_esc(CATEGORY_AUDIT_CHUNK_PREV)}</a>"
        )
    next_btn = ""
    if next_off < total_in_slice:
        next_btn = (
            f'<a href="{next_href}" class="btn btn-secondary btn-sm">'
            f"{_esc(CATEGORY_AUDIT_CHUNK_NEXT)}</a>"
        )
    return f"""
<p class="meta category-audit-chunk-meta">{_esc(meta)}</p>
<p class="category-audit-chunk-nav">{prev_btn} {next_btn}</p>
""".strip()


def category_audit_page_html(
    *,
    run_id: str,
    slice_rows: list[dict[str, Any]],
    chunk_rows: list[dict[str, Any]],
    filt: CategoryAuditFilter,
    stats: dict[str, Any],
    offset: int = 0,
    limit: int = DEFAULT_CHUNK_SIZE,
    reclassify_banner: str = "",
) -> str:
    slice_label = _esc(stats.get("slice_label") or filt.slice_label())
    slice_count = int(stats.get("total_in_slice") or 0)
    classified_total = int(stats.get("classified_in_run") or 0)
    run_total = int(stats.get("total_in_run") or 0)

    meta_line = (
        f"<strong>{slice_count}</strong> ticket{'s' if slice_count != 1 else ''} "
        f'in slice <span class="category-audit-slice-label">{slice_label}</span> '
        f"({classified_total} classified of {run_total} in run)."
    )
    if filt.include_tbc:
        meta_line += " Including manual-review (TBC) tickets."

    slice_empty_message = CATEGORY_AUDIT_SLICE_EMPTY
    if slice_count == 0 and run_total > 0 and classified_total == 0 and not filt.includes_tbc_rows():
        slice_empty_message = CATEGORY_AUDIT_SLICE_EMPTY_ALL_TBC

    preview_href = f"/run/{_esc(run_id)}/results#ticket-preview"

    filter_qs = filt.to_query_string()
    sweeps_url = f"/run/{_esc(run_id)}/category_audit/sweeps"
    if filter_qs:
        sweeps_url += f"?{filter_qs}"

    json_blob = _embed_json_for_script(
        {
            "run_id": run_id,
            "filter": filt.as_dict(),
            "stats": stats,
            "sweeps_url": sweeps_url,
            "offset": offset,
            "limit": limit,
        }
    )

    return f"""
    <h1 class="page-header">{_esc(CATEGORY_AUDIT_PAGE_TITLE)}</h1>
    <p class="meta">{_esc(CATEGORY_AUDIT_PAGE_INTRO)}</p>
    {reclassify_banner}
    <p class="links category-audit-nav">
      <a href="/run/{_esc(run_id)}/results" class="btn btn-secondary">{_esc(CATEGORY_AUDIT_RESULTS_LINK)}</a>
      <a href="{_esc(preview_href)}" class="btn btn-secondary">{_esc(CATEGORY_AUDIT_PREVIEW_LINK)}</a>
      <button type="button" class="btn btn-secondary" id="category-audit-reclassify-btn">Re-classify run</button>
    </p>
    <div id="category-audit-app" class="category-audit-app"
      data-run-id="{_esc(run_id)}"
      data-filter-q="{_esc(filt.q)}"
      data-filter-tier1="{_esc(filt.tier1)}"
      data-filter-tier4="{_esc(filt.tier4)}"
      data-filter-categories="{_esc(",".join(filt.categories))}"
      data-filter-include-tbc="{"true" if filt.include_tbc else "false"}"
      data-sweeps-url="{_esc(sweeps_url)}">
      <div class="category-audit-toolbar tbc-filter-bar">
        <form id="category-audit-filter-form" class="tbc-filter-bar" method="get"
          action="/run/{_esc(run_id)}/category_audit">
          <label class="tbc-filter-field">
            <span class="tbc-filter-label">Search</span>
            <input type="search" name="q" class="tbc-filter-input" value="{_esc(filt.q)}"
              placeholder="subject, body, tags" autocomplete="off" />
          </label>
          <label class="tbc-filter-field">
            <span class="tbc-filter-label">Segment</span>
            <select name="tier1" class="tbc-filter-select">
              <option value="">Any</option>
              <option value="B2C"{" selected" if filt.tier1 == "B2C" else ""}>B2C</option>
              <option value="B2B"{" selected" if filt.tier1 == "B2B" else ""}>B2B</option>
            </select>
          </label>
          <label class="tbc-filter-field tbc-filter-field--wide">
            <span class="tbc-filter-label">{_esc(CATEGORY_FILTER_LABEL)}</span>
            <input type="search" name="tier4" class="tbc-filter-input" value="{_esc(filt.tier4)}"
              placeholder="e.g. Cancellation Request" autocomplete="off" />
          </label>
          <label class="tbc-filter-field tbc-filter-field--wide">
            <span class="tbc-filter-label">Category keywords</span>
            <input type="search" name="categories" class="tbc-filter-input"
              value="{_esc(",".join(filt.categories))}"
              placeholder="comma-separated" autocomplete="off" />
          </label>
          <label class="tbc-filter-field tbc-filter-field--check">
            <input type="checkbox" name="include_tbc" value="1"
              {"checked" if filt.include_tbc else ""} />
            <span class="tbc-filter-label">{_esc(CATEGORY_AUDIT_INCLUDE_TBC_LABEL)}</span>
          </label>
          <button type="submit" class="btn btn-secondary btn-sm">Apply filters</button>
        </form>
      </div>
      <p class="meta category-audit-meta" role="status">{meta_line}</p>
      <p id="category-audit-status" class="meta tbc-filter-nl-status" hidden aria-live="polite"></p>

      <section class="category-audit-tickets-section" aria-labelledby="category-audit-tickets-heading">
        <h2 class="section-header" id="category-audit-tickets-heading">{_esc(CATEGORY_AUDIT_TICKETS_HEADING)}</h2>
        {_pagination_html(run_id=run_id, filt=filt, offset=offset, limit=limit, total_in_slice=slice_count)}
        {_ticket_cards_html(chunk_rows, run_id=run_id, empty_message=slice_empty_message)}
        {_pagination_html(run_id=run_id, filt=filt, offset=offset, limit=limit, total_in_slice=slice_count)}
      </section>

      <script type="application/json" id="category-audit-data">{json_blob}</script>
    </div>
    """.strip()


def build_category_audit_context(
    rows: list[dict[str, Any]],
    filt: CategoryAuditFilter,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from cs_tickets.category_audit_filters import category_audit_slice_stats

    effective = filt if filt.active else CategoryAuditFilter(include_tbc=filt.include_tbc)
    slice_rows = filter_category_audit_rows(rows, effective)
    stats = category_audit_slice_stats(rows, slice_rows, effective)
    return slice_rows, stats
