"""Tests for category audit duplicate detection."""

from __future__ import annotations

from cs_tickets.category_audit_duplicates import (
    duplicate_groups,
    duplicate_matched_ids,
    normalize_subject,
)


def test_normalize_subject_strips_re_fw_prefixes() -> None:
    assert normalize_subject("Re: Fw: Cancel my plan") == "cancel my plan"
    assert normalize_subject("  RE:  Hello  ") == "hello"


def test_duplicate_groups_same_sender_and_subject() -> None:
    rows = [
        {
            "id": "1",
            "requester_email": "user@example.com",
            "subject": "Webhook retry",
        },
        {
            "id": "2",
            "requester_email": "user@example.com",
            "subject": "Re: Webhook retry",
        },
        {
            "id": "3",
            "requester_email": "other@example.com",
            "subject": "Webhook retry",
        },
    ]
    groups = duplicate_groups(rows)
    assert groups == [("1", "2")]
    assert duplicate_matched_ids(rows) == ["1", "2"]


def test_duplicate_groups_ignores_missing_email_or_subject() -> None:
    rows = [
        {"id": "1", "requester_email": "", "subject": "A"},
        {"id": "2", "requester_email": "a@b.com", "subject": ""},
    ]
    assert duplicate_groups(rows) == []
