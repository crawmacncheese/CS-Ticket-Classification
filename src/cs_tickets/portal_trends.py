"""Portal HTML for the TBC trends dashboard."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cs_tickets.portal_layout import portal_page_html
from cs_tickets.tbc_trends import (
    DashboardSnapshot,
    TrendEvent,
    WeeklyRollupRow,
    dashboard_snapshot,
    load_export_summary,
    load_subject_cluster_rollup,
    load_tag_rollup,
    load_tbc_reason_rollup,
    load_weekly_rollup,
    trends_events_path,
    trends_snapshot_enabled,
)

DASHBOARD_TITLE = "TBC trends"
DASHBOARD_INTRO = (
    "Manual review (TBC) rate and hotspots by week, tag, and subject cluster. "
    "Data comes from classified export snapshots."
)


def _h(s: object) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pct_bar(pct: float, *, max_pct: float = 100.0) -> str:
    width = min(100.0, max(0.0, (pct / max_pct) * 100.0 if max_pct else 0.0))
    return f'<span class="trend-bar" style="width:{width:.1f}%"></span>'


def dashboard_headline_html(snapshot: DashboardSnapshot) -> str:
    if snapshot.total_tickets:
        pct = 100.0 * snapshot.total_tbc / snapshot.total_tickets
        pct_str = f"{pct:.1f}%"
    else:
        pct_str = "0.0%"
    version_line = ""
    if snapshot.classifier_version:
        version_line = (
            f'<span class="run-summary-meta">Classifier <code>{_h(snapshot.classifier_version)}</code></span>'
        )
    return f"""
<div class="run-summary trends-headline" role="status">
  <span class="run-summary-lead">{snapshot.total_tickets} tickets tracked</span>
  <span class="run-summary-tbc">
    {snapshot.total_tbc} need manual review <span class="run-summary-tbc-hint">(TBC)</span>
    <span class="run-summary-tbc-pct">— {pct_str}</span>
  </span>
  <span class="run-summary-split">
    {snapshot.week_count} week bucket(s) · {snapshot.export_count} snapshot(s)
  </span>
  {version_line}
</div>""".strip()


def weekly_trend_table_html(rows: list[WeeklyRollupRow]) -> str:
    if not rows:
        return '<p class="meta">No weekly data yet.</p>'
    max_pct = max((r.tbc_pct for r in rows), default=1.0) or 1.0
    body: list[str] = []
    for i, r in enumerate(rows):
        row_cls = "zebra-even" if i % 2 == 1 else "zebra-odd"
        body.append(
            f"<tr class='{row_cls}'>"
            f"<td class='txt'>{_h(r.week_bucket)}</td>"
            f"<td class='num'>{r.total}</td>"
            f"<td class='num'>{r.tbc_count}</td>"
            f"<td class='num'>{r.tbc_pct:.1f}%</td>"
            f"<td class='num'>{r.tbc_b2b}</td>"
            f"<td class='num'>{r.tbc_b2c}</td>"
            f"<td class='trend-bar-cell'>{_pct_bar(r.tbc_pct, max_pct=max_pct)}</td>"
            f"</tr>"
        )
    headers = ["Week", "Tickets", "TBC", "TBC %", "B2B TBC", "B2C TBC", "Trend"]
    th = "".join(f"<th>{_h(c)}</th>" for c in headers)
    return f"""
<table class="stats-table trends-table" aria-label="Weekly TBC rate">
  <thead><tr>{th}</tr></thead>
  <tbody>{"".join(body)}</tbody>
</table>""".strip()


def tag_hotspots_table_html(tag_rows: list[dict[str, Any]], *, latest_week_only: bool = True) -> str:
    if not tag_rows:
        return '<p class="meta">No TBC tag data.</p>'
    rows = tag_rows
    if latest_week_only:
        latest = max(r["week_bucket"] for r in tag_rows)
        rows = [r for r in tag_rows if r["week_bucket"] == latest][:15]
    max_count = max((r["tbc_count"] for r in rows), default=1) or 1
    body: list[str] = []
    for i, r in enumerate(rows):
        row_cls = "zebra-even" if i % 2 == 1 else "zebra-odd"
        body.append(
            f"<tr class='{row_cls}'>"
            f"<td class='txt'>{_h(r['week_bucket'])}</td>"
            f"<td class='txt'><code>{_h(r['tag'])}</code></td>"
            f"<td class='num'>{r['tbc_count']}</td>"
            f"<td class='trend-bar-cell'>{_pct_bar(float(r['tbc_count']), max_pct=float(max_count))}</td>"
            f"</tr>"
        )
    th = "".join(f"<th>{_h(c)}</th>" for c in ["Week", "Tag", "TBC count", ""])
    return f"""
<table class="stats-table trends-table" aria-label="Top TBC tags">
  <thead><tr>{th}</tr></thead>
  <tbody>{"".join(body)}</tbody>
</table>""".strip()


def subject_cluster_table_html(cluster_rows: list[dict[str, Any]], *, limit: int = 15) -> str:
    if not cluster_rows:
        return '<p class="meta">No subject cluster data.</p>'
    ranked = sorted(cluster_rows, key=lambda x: x["tbc_count"], reverse=True)[:limit]
    max_count = max((r["tbc_count"] for r in ranked), default=1) or 1
    body: list[str] = []
    for i, r in enumerate(ranked):
        row_cls = "zebra-even" if i % 2 == 1 else "zebra-odd"
        sample = _h(r["sample_subject"][:100])
        body.append(
            f"<tr class='{row_cls}'>"
            f"<td class='txt'>{_h(r['week_bucket'])}</td>"
            f"<td class='txt'><code>{_h(r['subject_cluster'][:80])}</code></td>"
            f"<td class='txt cluster-sample'>{sample}</td>"
            f"<td class='num'>{r['tbc_count']}</td>"
            f"<td class='trend-bar-cell'>{_pct_bar(float(r['tbc_count']), max_pct=float(max_count))}</td>"
            f"</tr>"
        )
    th = "".join(
        f"<th>{_h(c)}</th>" for c in ["Week", "Cluster", "Example subject", "TBC", ""]
    )
    return f"""
<table class="stats-table trends-table" aria-label="Top subject clusters">
  <thead><tr>{th}</tr></thead>
  <tbody>{"".join(body)}</tbody>
</table>""".strip()


def tbc_reason_table_html(reason_rows: list[dict[str, Any]]) -> str:
    if not reason_rows:
        return '<p class="meta">No TBC reason data.</p>'
    by_week: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in reason_rows:
        by_week[r["week_bucket"]].append(r)
    body: list[str] = []
    for i, week in enumerate(sorted(by_week)):
        parts = ", ".join(f"{_h(r['tbc_reason'])}: {r['tbc_count']}" for r in by_week[week])
        row_cls = "zebra-even" if i % 2 == 1 else "zebra-odd"
        body.append(f"<tr class='{row_cls}'><td class='txt'>{_h(week)}</td><td class='txt'>{parts}</td></tr>")
    th = "".join(f"<th>{_h(c)}</th>" for c in ["Week", "Reason mix"])
    return f"""
<table class="stats-table trends-table" aria-label="TBC reason mix by week">
  <thead><tr>{th}</tr></thead>
  <tbody>{"".join(body)}</tbody>
</table>""".strip()


def exports_table_html(exports: list[dict[str, Any]]) -> str:
    if not exports:
        return '<p class="meta">No snapshots ingested yet.</p>'
    body: list[str] = []
    for i, ex in enumerate(exports):
        row_cls = "zebra-even" if i % 2 == 1 else "zebra-odd"
        rows_n = int(ex["row_count"])
        tbc_n = int(ex["tbc_count"])
        pct = 100.0 * tbc_n / rows_n if rows_n else 0.0
        body.append(
            f"<tr class='{row_cls}'>"
            f"<td class='txt'><code>{_h(ex['export_id'])}</code></td>"
            f"<td class='num'>{rows_n}</td>"
            f"<td class='num'>{tbc_n} ({pct:.1f}%)</td>"
            f"<td class='txt'>{_h(ex['captured_at'])}</td>"
            f"<td class='txt'><code>{_h(ex['classifier_version'])}</code></td>"
            f"</tr>"
        )
    th = "".join(f"<th>{_h(c)}</th>" for c in ["Export", "Rows", "TBC", "Captured", "Classifier"])
    return f"""
<table class="stats-table trends-table" aria-label="Ingested snapshots">
  <thead><tr>{th}</tr></thead>
  <tbody>{"".join(body)}</tbody>
</table>""".strip()


def trend_events_html(events: list[TrendEvent]) -> str:
    if not events:
        return ""
    items = "".join(
        f"<li><time datetime='{_h(e.date)}'>{_h(e.date)}</time> — {_h(e.label)}</li>"
        for e in events
    )
    return f"""
<h2 class="section-header">Rule batches &amp; milestones</h2>
<p class="meta">From <code>events.json</code> (optional).</p>
<ul class="trend-events">{items}</ul>""".strip()


def dashboard_body_html(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    events: list[TrendEvent] | None = None,
) -> str:
    snapshot = dashboard_snapshot(conn)
    weekly = load_weekly_rollup(conn)
    tag_rows = load_tag_rollup(conn, top_n=15)
    cluster_rows = load_subject_cluster_rollup(conn, top_n=20)
    reason_rows = load_tbc_reason_rollup(conn)
    exports = load_export_summary(conn)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    auto_note = ""
    if trends_snapshot_enabled():
        auto_note = (
            '<p class="meta trends-auto-note">Auto-snapshot on upload is <strong>enabled</strong> '
            "(<code>TBC_TRENDS_ENABLED</code>).</p>"
        )
    events_block = trend_events_html(events or [])
    return f"""
<p class="meta trends-generated">Updated {generated} · DB: <code>{_h(db_path)}</code></p>
{auto_note}
{dashboard_headline_html(snapshot)}

<h2 class="section-header">Weekly TBC rate</h2>
<p class="meta">ISO week of ticket <code>created_at</code>.</p>
<div class="stats-wrap">{weekly_trend_table_html(weekly)}</div>

<h2 class="section-header">Top TBC tags</h2>
<p class="meta">Tags on manual-review tickets (latest week when available).</p>
<div class="stats-wrap">{tag_hotspots_table_html(tag_rows)}</div>

<h2 class="section-header">Subject clusters</h2>
<p class="meta">Normalized subject fingerprints on TBC rows.</p>
<div class="stats-wrap">{subject_cluster_table_html(cluster_rows)}</div>

<h2 class="section-header">Why TBC</h2>
<p class="meta">Classifier reason buckets per week.</p>
<div class="stats-wrap">{tbc_reason_table_html(reason_rows)}</div>

{events_block}

<h2 class="section-header">Snapshots</h2>
<div class="stats-wrap">{exports_table_html(exports)}</div>
""".strip()


def dashboard_empty_html(*, db_path: Path, repo_root: Path) -> str:
    snapshot_hint = ""
    if trends_snapshot_enabled():
        snapshot_hint = (
            "<p class='meta'>Auto-snapshot is enabled — upload an export on the "
            "<a href='/'>Classify</a> page, or run "
            "<code>tools/tbc_trend_snapshot.py</code>.</p>"
        )
    else:
        snapshot_hint = (
            "<p class='meta'>Enable <code>TBC_TRENDS_ENABLED=1</code> to snapshot each portal upload, "
            "or run <code>tools/tbc_trend_snapshot.py --ndjson-dir data/</code>.</p>"
        )
    events_path = trends_events_path(repo_root)
    return f"""
<p class="meta">No trend database at <code>{_h(db_path)}</code> yet.</p>
{snapshot_hint}
<p class="meta">Optional milestones file: <code>{_h(events_path)}</code></p>
""".strip()


def dashboard_page_html(
    *,
    body: str,
    title: str = DASHBOARD_TITLE,
) -> str:
    page_body = f"""
    <h1 class="page-header">{_h(title)}</h1>
    <p class="meta">{DASHBOARD_INTRO}</p>
    {body}
    """
    return portal_page_html(
        title=title,
        active="dashboard",
        body_class="trends-page",
        body=page_body,
    )
