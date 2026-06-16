"""Ticket id formatting helpers for feedback workbooks."""

from __future__ import annotations


def normalize_ticket_id(value: object) -> str:
    """Format workbook ticket ids as clean integer strings (Excel often stores them as floats)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value).strip()
    raw = str(value).strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        return raw[:-2]
    return raw
