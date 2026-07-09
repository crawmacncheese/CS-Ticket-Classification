"""CSV export for category audit slices."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from cs_tickets.schema import TIER_COLUMNS

CATEGORY_AUDIT_CSV_COLUMNS: tuple[str, ...] = (
    "id",
    "subject",
    "requester_email",
    "description",
    *TIER_COLUMNS,
    "tags",
    "created_at",
)


def _format_tags(tags: object) -> str:
    if tags is None:
        return ""
    if isinstance(tags, list):
        return ", ".join(str(t) for t in tags)
    if isinstance(tags, str):
        try:
            parsed = json.loads(tags)
            if isinstance(parsed, list):
                return ", ".join(str(t) for t in parsed)
        except json.JSONDecodeError:
            pass
        return tags
    return str(tags)


def category_audit_row_to_csv(row: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for col in CATEGORY_AUDIT_CSV_COLUMNS:
        if col == "tags":
            out[col] = _format_tags(row.get("tags"))
        else:
            val = row.get(col)
            out[col] = "" if val is None else str(val)
    return out


def category_audit_slice_csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.DictWriter(buf, fieldnames=list(CATEGORY_AUDIT_CSV_COLUMNS), extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(category_audit_row_to_csv(row))
    return buf.getvalue().encode("utf-8")
