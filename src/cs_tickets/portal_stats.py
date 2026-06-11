"""Build pivot-style tier count tables for portal UI."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

TIER_KEYS = ("Tier1_Segment", "Tier2_Stream", "Tier3_Cat", "Tier4_Type")


@dataclass(frozen=True)
class ClassifyRunCounts:
    total: int
    tbc: int
    tbc_b2b: int
    tbc_b2c: int


def is_manual_review_row(row: dict[str, Any]) -> bool:
    """Match audit-style TBC: Tier4 contains 'tbc' (case-insensitive)."""
    tier4 = str(row.get("Tier4_Type") or "").lower()
    return "tbc" in tier4


def classify_run_counts(rows: list[dict[str, Any]]) -> ClassifyRunCounts:
    total = len(rows)
    tbc_rows = [r for r in rows if is_manual_review_row(r)]
    tbc_b2b = sum(1 for r in tbc_rows if str(r.get("Tier1_Segment") or "") == "B2B")
    tbc_b2c = sum(1 for r in tbc_rows if str(r.get("Tier1_Segment") or "") == "B2C")
    return ClassifyRunCounts(
        total=total,
        tbc=len(tbc_rows),
        tbc_b2b=tbc_b2b,
        tbc_b2c=tbc_b2c,
    )


def classify_run_summary_html(rows: list[dict[str, Any]], *, warns: int = 0) -> str:
    """Prominent run summary: total categorized, manual review (TBC), B2B/B2C split."""
    counts = classify_run_counts(rows)
    if counts.total:
        tbc_pct = f"{100.0 * counts.tbc / counts.total:.1f}%"
    else:
        tbc_pct = "0.0%"
    warn_line = ""
    if warns:
        warn_line = (
            f'<span class="run-summary-meta">'
            f"{warns} technical warning{'s' if warns != 1 else ''}"
            f"</span>"
        )
    return f"""
<div class="run-summary classify-run-summary" role="status">
  <span class="run-summary-lead">{counts.total} tickets categorized</span>
  <span class="run-summary-tbc">
    {counts.tbc} need manual review <span class="run-summary-tbc-hint">(TBC)</span>
    <span class="run-summary-tbc-pct">— {tbc_pct}</span>
  </span>
  <span class="run-summary-split">B2B: {counts.tbc_b2b} · B2C: {counts.tbc_b2c}</span>
  {warn_line}
</div>""".strip()


def tier_stats_display_rows(rows: list[dict[str, Any]]) -> tuple[list[list[str]], int]:
    """Return body rows [t1,t2,t3,t4,count_str] with pivot-style blanks for repeated parents, plus grand total."""
    c: Counter[tuple[str, str, str, str]] = Counter()
    for r in rows:
        key = tuple(str(r.get(k) or "").strip() for k in TIER_KEYS)
        c[key] += 1
    sorted_items = sorted(c.items(), key=lambda x: x[0])
    prev: tuple[str | None, str | None, str | None, str | None] = (None, None, None, None)
    out: list[list[str]] = []
    grand = 0
    for (t1, t2, t3, t4), n in sorted_items:
        grand += n
        c1 = t1 if prev[0] is None or t1 != prev[0] else ""
        c2 = t2 if prev[0] is None or t1 != prev[0] or t2 != prev[1] else ""
        c3 = t3 if prev[0] is None or t1 != prev[0] or t2 != prev[1] or t3 != prev[2] else ""
        c4 = t4
        out.append([c1, c2, c3, c4, str(n)])
        prev = (t1, t2, t3, t4)
    return out, grand


def tier_stats_sheet_rows(rows: list[dict[str, Any]]) -> tuple[list[str], list[list[str | int]]]:
    """Header + rows for spreadsheet export: pivot-style tiers, integer counts, trailing Grand Total row."""
    body, grand = tier_stats_display_rows(rows)
    header = ["Tier1_Segment", "Tier2_Stream", "Tier3_Cat", "Tier4_Type", "COUNTA of id"]
    data: list[list[str | int]] = []
    for r in body:
        t1, t2, t3, t4, c = r
        data.append([t1, t2, t3, t4, int(c)])
    data.append(["Grand Total", "", "", "", grand])
    return header, data


def tier_stats_table_html(rows: list[dict[str, Any]]) -> str:
    """HTML table: Tier1–Tier4 + COUNTA of id, pivot-style blanks, grand total row."""
    body, grand = tier_stats_display_rows(rows)
    headers = ["Tier1_Segment", "Tier2_Stream", "Tier3_Cat", "Tier4_Type", "COUNTA of id"]
    th = "".join(f"<th>{_h(c)}</th>" for c in headers)
    trs: list[str] = []
    for i, r in enumerate(body):
        row_cls = "zebra-even" if i % 2 == 1 else "zebra-odd"
        trs.append(
            "<tr class='"
            + row_cls
            + "'>"
            + "".join(f"<td class='{_cell_class(j)}'>{_h(x)}</td>" for j, x in enumerate(r))
            + "</tr>"
        )
    gt = "".join(
        f"<td class='{_cell_class(j)} grand'>{_h(x)}</td>"
        for j, x in enumerate(["Grand Total", "", "", "", str(grand)])
    )
    return f"""
<table class="stats-table" aria-label="Tier counts for this run">
  <thead><tr>{th}</tr></thead>
  <tbody>
    {"".join(trs)}
    <tr class="grand-total">{gt}</tr>
  </tbody>
</table>
""".strip()


def _h(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _cell_class(col_index: int) -> str:
    return "num" if col_index == 4 else "txt"
