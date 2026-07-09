"""Tests for category audit slice checks."""

from __future__ import annotations

from cs_tickets.category_audit_sweeps import run_category_audit_sweeps


def test_empty_slice_returns_zero_duplicate_matches() -> None:
    sweeps = run_category_audit_sweeps([])
    dup = next((s for s in sweeps if s.id == "possible_duplicates"), None)
    assert dup is not None
    assert dup.match_count == 0


def test_duplicate_sweep_finds_groups() -> None:
    rows = [
        {
            "id": "100",
            "requester_email": "webhook@corp.com",
            "subject": "Order failed",
        },
        {
            "id": "101",
            "requester_email": "webhook@corp.com",
            "subject": "Re: Order failed",
        },
    ]
    sweeps = run_category_audit_sweeps(rows)
    dup = next((s for s in sweeps if s.id == "possible_duplicates"), None)
    assert dup is not None
    assert dup.match_count == 2
    assert dup.matched_groups == (("100", "101"),)
