from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cs_tickets.classify import attach_tiers
from cs_tickets.satisfaction import has_bad_satisfaction_rating
from cs_tickets.schema import MASTER_COLUMNS
from cs_tickets.taxonomy import AllowList
from cs_tickets.thread_enrich import (
    build_ticket_index,
    flatten_for_classify,
    thread_enrichment_enabled,
)


def _dict_tickets_from_top(data: Any) -> Iterator[dict[str, Any]]:
    if isinstance(data, dict):
        yield data
    elif isinstance(data, list):
        for el in data:
            if isinstance(el, dict):
                yield el


def _dicts_from_json_text(text: str) -> Iterator[dict[str, Any]]:
    """Parse buffer as one JSON value, or multiple concatenated JSON values (JSONL / NDJSON blob)."""
    s = text.strip()
    if not s:
        raise ValueError("Export file is empty.")

    try:
        doc = json.loads(s)
    except json.JSONDecodeError:
        pass
    else:
        yield from _dict_tickets_from_top(doc)
        return

    dec = json.JSONDecoder()
    idx = 0
    n = len(s)
    count = 0
    while idx < n:
        while idx < n and s[idx] in " \t\r\n":
            idx += 1
        if idx >= n:
            break
        start = idx
        try:
            val, end = dec.raw_decode(s, idx)
        except json.JSONDecodeError as e:
            raise ValueError(
                "Could not parse export as JSON. Expected NDJSON (one ticket JSON per line), "
                "a single JSON object or array, or multiple JSON objects one after another."
            ) from e
        idx = end
        if isinstance(val, dict):
            yield val
            count += 1
        elif isinstance(val, list):
            for d in _dict_tickets_from_top(val):
                yield d
                count += 1
        else:
            raise ValueError(
                f"Expected JSON objects or arrays of objects; got {type(val).__name__} at offset {start}."
            )
    if count == 0:
        raise ValueError("No JSON ticket objects found in export.")


def _iter_ticket_dicts(export_path: Path) -> Iterator[dict[str, Any]]:
    """Yield Zendesk-style ticket dicts from NDJSON, a single JSON value, or concatenated JSON objects.

    NDJSON = one complete JSON value per line (typical Zendesk export). Pretty-printed
    multi-line single object / array is supported by parsing the whole file when the
    first non-empty line is not a complete JSON value. Multiple minified objects on one
    line (``{...}{...}``) are handled via ``JSONDecoder.raw_decode`` on the full buffer.
    """
    with export_path.open(encoding="utf-8-sig") as f:
        first_nonempty = ""
        while True:
            line = f.readline()
            if not line:
                return
            s = line.strip()
            if s:
                first_nonempty = s
                break

        try:
            first_val = json.loads(first_nonempty)
        except json.JSONDecodeError:
            yield from _dicts_from_json_text(export_path.read_text(encoding="utf-8-sig"))
            return

        if isinstance(first_val, list):
            yield from _dict_tickets_from_top(first_val)
            return

        if isinstance(first_val, dict):
            yield first_val
            line_no = 1
            for line in f:
                line_no += 1
                s = line.strip()
                if not s:
                    continue
                try:
                    val = json.loads(s)
                except json.JSONDecodeError as e:
                    raise ValueError(
                        f"Invalid JSON on line {line_no} of export (NDJSON mode). "
                        "If this file is one pretty-printed ticket, re-save as one JSON object "
                        "without extra non-JSON lines after the first object, or use one JSON object per line."
                    ) from e
                if isinstance(val, dict):
                    yield val
                elif isinstance(val, list):
                    yield from _dict_tickets_from_top(val)
                else:
                    raise ValueError(
                        f"Line {line_no}: expected a JSON object or array of objects, got {type(val).__name__}."
                    )
            return

        raise ValueError(
            f"First JSON value must be an object or array of objects, got {type(first_val).__name__}."
        )


def iter_master_rows(
    ndjson_path: Path,
    allow: AllowList,
    *,
    limit: int | None = None,
    bad_satisfaction_only: bool = False,
) -> Iterator[tuple[dict[str, Any], str | None]]:
    """Stream ticket exports → full master-column dicts + optional per-row warning."""
    if thread_enrichment_enabled():
        tickets = list(_iter_ticket_dicts(ndjson_path))
        thread_index = build_ticket_index(tickets)
        ticket_source: Iterator[dict[str, Any]] = iter(tickets)
    else:
        thread_index = {}
        ticket_source = _iter_ticket_dicts(ndjson_path)
    n = 0
    for ticket in ticket_source:
        if bad_satisfaction_only and not has_bad_satisfaction_rating(ticket):
            continue
        base = flatten_for_classify(ticket, thread_index)
        row, warn = attach_tiers(base, allow)
        yield row, warn
        n += 1
        if limit is not None and n >= limit:
            break


def format_cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def write_master_csv(rows: Iterator[dict[str, Any]], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(MASTER_COLUMNS), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: format_cell(row.get(k)) for k in MASTER_COLUMNS})
            count += 1
    return count


def run_to_csv(
    ndjson_path: Path,
    allow: AllowList,
    out_path: Path,
    *,
    limit: int | None = None,
    bad_satisfaction_only: bool = False,
) -> tuple[int, int]:
    """Run pipeline and write CSV. Returns (row_count, warning_count)."""
    warns = 0

    def rows_only() -> Iterator[dict[str, Any]]:
        nonlocal warns
        for row, warn in iter_master_rows(
            ndjson_path,
            allow,
            limit=limit,
            bad_satisfaction_only=bad_satisfaction_only,
        ):
            if warn:
                warns += 1
            yield row

    n = write_master_csv(rows_only(), out_path)
    return n, warns
