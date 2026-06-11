import json

import pytest

from cs_tickets.thread_enrich import (
    INTERNAL_ENRICHMENT_KEYS,
    build_ticket_index,
    enrichment_for_row,
    flatten_for_classify,
    is_reply_ticket,
    merge_enrichment,
    parent_ticket_id,
    strip_enrichment,
)


def _base_ticket(**overrides: object) -> dict:
    row = {
        "url": "https://example.zendesk.com/api/v2/tickets/1.json",
        "id": 1,
        "external_id": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "generated_timestamp": 1,
        "type": "question",
        "subject": "Help",
        "raw_subject": "Help",
        "description": "Body",
        "priority": "normal",
        "status": "open",
        "follower_ids": [],
        "email_cc_ids": [],
        "forum_topic_id": None,
        "problem_id": None,
        "has_incidents": False,
        "is_public": True,
        "due_at": None,
        "tags": [],
    }
    row.update(overrides)
    return row


def test_is_reply_ticket_subject_prefix() -> None:
    assert is_reply_ticket(_base_ticket(subject="RE: Renewal question"))
    assert not is_reply_ticket(_base_ticket(subject="Renewal question"))


def test_parent_ticket_id_from_via_follow_up() -> None:
    ticket = _base_ticket(
        via={"source": {"rel": "follow_up", "from": {"ticket_id": 42}}},
    )
    assert parent_ticket_id(ticket) == 42


def test_enrichment_merges_parent_tags_for_reply() -> None:
    parent = _base_ticket(
        id=100,
        tags=["existing_subscriber", "digital"],
        subject="Renewal help",
        description="I need to renew.",
    )
    child = _base_ticket(
        id=101,
        tags=["miscellaneous"],
        subject="RE: Renewal help",
        description="Thanks",
        via={"source": {"rel": "follow_up", "from": {"ticket_id": 100}}},
    )
    index = build_ticket_index([parent, child])
    enrichment = enrichment_for_row(child, index)
    assert enrichment["_parent_ticket_id"] == 100
    assert enrichment["_is_reply"] is True
    merged = json.loads(enrichment["_enriched_tags"])
    assert merged == ["miscellaneous", "existing_subscriber", "digital"]
    assert "renewal help" in enrichment["_thread_blob"]


def test_enrichment_skipped_when_parent_missing() -> None:
    child = _base_ticket(
        id=101,
        subject="RE: Missing parent",
        via={"source": {"rel": "follow_up", "from": {"ticket_id": 999}}},
    )
    index = build_ticket_index([child])
    assert enrichment_for_row(child, index) == {}


def test_flatten_for_classify_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CS_TICKETS_THREAD_ENRICHMENT", "0")
    parent = _base_ticket(id=10, tags=["refund"], subject="Refund", description="Please refund")
    child = _base_ticket(
        id=11,
        tags=[],
        subject="RE: Refund",
        description="See below",
        via={"source": {"rel": "follow_up", "from": {"ticket_id": 10}}},
    )
    index = build_ticket_index([parent, child])
    row = flatten_for_classify(child, index)
    assert "_enriched_tags" not in row


def test_flatten_for_classify_and_strip_enrichment() -> None:
    parent = _base_ticket(id=10, tags=["refund"], subject="Refund", description="Please refund")
    child = _base_ticket(
        id=11,
        tags=[],
        subject="RE: Refund",
        description="See below",
        via={"source": {"rel": "follow_up", "from": {"ticket_id": 10}}},
    )
    index = build_ticket_index([parent, child])
    row = flatten_for_classify(child, index)
    assert "_enriched_tags" in row
    assert "id" in row
    cleaned = strip_enrichment(row)
    assert not INTERNAL_ENRICHMENT_KEYS.intersection(cleaned)
    assert cleaned["id"] == 11
