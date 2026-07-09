from __future__ import annotations

import json
from typing import Any

from cs_tickets.schema import BASE_COLUMNS


def extract_requester_email(ticket: dict[str, Any]) -> str | None:
    """Lowercase requester email from Zendesk ticket dict (API or flat export)."""
    raw = ticket.get("requester_email")
    if raw:
        return str(raw).strip().lower()
    requester = ticket.get("requester")
    if isinstance(requester, dict):
        email = requester.get("email")
        if email:
            return str(email).strip().lower()
    return None


def _json_compact(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def flatten_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    """Map one Zendesk API ticket dict to BASE_COLUMNS (no tier columns)."""
    tags = ticket.get("tags")
    if isinstance(tags, list):
        tags_s = json.dumps(tags, separators=(",", ":"), ensure_ascii=False)
    elif tags is None:
        tags_s = None
    else:
        tags_s = str(tags)

    def listish(key: str) -> str | None:
        v = ticket.get(key)
        if v is None:
            return None
        if isinstance(v, list):
            return json.dumps(v, separators=(",", ":"), ensure_ascii=False)
        return str(v)

    row: dict[str, Any] = {}
    for col in BASE_COLUMNS:
        if col == "tags":
            row[col] = tags_s
            continue
        if col in ("follower_ids", "email_cc_ids"):
            row[col] = listish(col)
            continue
        val = ticket.get(col)
        if col in ("has_incidents", "is_public") and val is not None:
            row[col] = bool(val)
        else:
            row[col] = val
    email = extract_requester_email(ticket)
    if email:
        row["requester_email"] = email
    return row
