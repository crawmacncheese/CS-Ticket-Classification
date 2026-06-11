from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from cs_tickets.flatten import flatten_ticket


def thread_enrichment_enabled() -> bool:
    """On by default. Set CS_TICKETS_THREAD_ENRICHMENT=0 to disable."""
    raw = os.environ.get("CS_TICKETS_THREAD_ENRICHMENT")
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in ("0", "false", "no")

INTERNAL_ENRICHMENT_KEYS = frozenset(
    {"_enriched_tags", "_parent_ticket_id", "_thread_blob", "_is_reply"}
)

_THREAD_BLOB_MAX = 1200


@dataclass(frozen=True)
class TicketThreadContext:
    """Lightweight parent slice for thread enrichment lookups."""

    tags: tuple[str, ...]
    subject: str
    description: str


def ticket_id(ticket: dict[str, Any]) -> int | None:
    raw = ticket.get("id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def parent_ticket_id(ticket: dict[str, Any]) -> int | None:
    via = ticket.get("via")
    if isinstance(via, dict):
        source = via.get("source")
        if isinstance(source, dict):
            from_obj = source.get("from")
            if isinstance(from_obj, dict):
                raw = from_obj.get("ticket_id")
                if raw is not None:
                    try:
                        return int(raw)
                    except (TypeError, ValueError):
                        pass
    raw_problem = ticket.get("problem_id")
    if raw_problem is not None:
        try:
            return int(raw_problem)
        except (TypeError, ValueError):
            return None
    return None


def is_reply_ticket(ticket: dict[str, Any]) -> bool:
    subject = (ticket.get("subject") or "").lower().strip()
    if subject.startswith("re:") or subject.startswith("fw:"):
        return True
    via = ticket.get("via")
    if isinstance(via, dict):
        source = via.get("source")
        if isinstance(source, dict) and source.get("rel") == "follow_up":
            return True
    return False


def _tags_as_list(ticket: dict[str, Any]) -> list[str]:
    tags = ticket.get("tags")
    if isinstance(tags, list):
        return [str(x).lower() for x in tags]
    if tags is None:
        return []
    return [str(tags).lower()]


def _slice_for_thread(ticket: dict[str, Any]) -> TicketThreadContext:
    return TicketThreadContext(
        tags=tuple(_tags_as_list(ticket)),
        subject=str(ticket.get("subject") or ""),
        description=str(ticket.get("description") or ""),
    )


def build_ticket_index(
    tickets: Iterable[dict[str, Any]],
) -> dict[int, TicketThreadContext]:
    index: dict[int, TicketThreadContext] = {}
    for ticket in tickets:
        tid = ticket_id(ticket)
        if tid is not None:
            index[tid] = _slice_for_thread(ticket)
    return index


def enrichment_for_row(
    ticket: dict[str, Any],
    index: dict[int, TicketThreadContext],
) -> dict[str, Any]:
    """Internal enrichment keys to merge onto a flattened row before classify."""
    if not is_reply_ticket(ticket):
        return {}
    pid = parent_ticket_id(ticket)
    if pid is None or pid not in index:
        return {}
    parent = index[pid]
    child_tags = _tags_as_list(ticket)
    merged: list[str] = []
    seen: set[str] = set()
    for tag in child_tags + list(parent.tags):
        if tag not in seen:
            seen.add(tag)
            merged.append(tag)
    c_subj = str(ticket.get("subject") or "")
    c_desc = str(ticket.get("description") or "")
    thread_blob = f"{parent.subject} {parent.description} {c_subj} {c_desc}".strip()
    if len(thread_blob) > _THREAD_BLOB_MAX:
        thread_blob = thread_blob[:_THREAD_BLOB_MAX]
    return {
        "_enriched_tags": json.dumps(merged, separators=(",", ":"), ensure_ascii=False),
        "_parent_ticket_id": pid,
        "_thread_blob": thread_blob.lower(),
        "_is_reply": True,
    }


def merge_enrichment(row: dict[str, Any], enrichment: dict[str, Any]) -> dict[str, Any]:
    if not enrichment:
        return row
    out = dict(row)
    out.update(enrichment)
    return out


def flatten_for_classify(
    ticket: dict[str, Any],
    index: dict[int, TicketThreadContext],
) -> dict[str, Any]:
    """Flatten a Zendesk ticket and attach thread enrichment when a parent is in the index."""
    row = flatten_ticket(ticket)
    if not thread_enrichment_enabled():
        return row
    return merge_enrichment(row, enrichment_for_row(ticket, index))


def strip_enrichment(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in INTERNAL_ENRICHMENT_KEYS}
