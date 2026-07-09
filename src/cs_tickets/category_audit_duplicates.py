"""Duplicate detection within a category audit slice."""

from __future__ import annotations

import re
from typing import Any

DUPLICATE_SWEEP_ID = "possible_duplicates"


def normalize_subject(subject: str) -> str:
    """Lowercase subject with Re:/Fw: prefixes stripped for grouping."""
    s = (subject or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    while True:
        m = re.match(r"^(re|fw|fwd):\s*", s)
        if not m:
            break
        s = s[m.end() :].strip()
    return s


def duplicate_groups(rows: list[dict[str, Any]]) -> list[tuple[str, ...]]:
    """Ticket id groups sharing requester email + normalized subject (count > 1)."""
    buckets: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        email = str(row.get("requester_email") or "").strip().lower()
        subj = normalize_subject(str(row.get("subject") or ""))
        if not email or not subj:
            continue
        key = (email, subj)
        tid = str(row.get("id") or "")
        if tid:
            buckets.setdefault(key, []).append(tid)
    return [tuple(ids) for ids in buckets.values() if len(ids) > 1]


def duplicate_matched_ids(rows: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for group in duplicate_groups(rows):
        ids.extend(group)
    return ids


def duplicate_matched_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    id_set = set(duplicate_matched_ids(rows))
    if not id_set:
        return []
    return [row for row in rows if str(row.get("id") or "") in id_set]
