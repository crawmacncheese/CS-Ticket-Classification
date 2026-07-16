"""Tests for natural-language TBC review focus parsing."""

from __future__ import annotations

from cs_tickets.taxonomy import AllowList

from cs_tickets.tbc_filter_nl import (
    build_filter_batch_rule_prefill,
    parse_review_focus_deterministic,
)
from cs_tickets.tbc_queue_filters import TbcQueueFilter


def test_parse_contains_and_move_to_print() -> None:
    allow = AllowList(tuples=frozenset({("B2C", "Service Task", "Print", "Delivery", "N/A")}))
    result = parse_review_focus_deterministic(
        "anything contains sherina needs to be move under Print",
        allow,
    )
    assert result.ok
    assert result.filter.q.lower() == "sherina"
    assert "Print" in result.filter.categories or result.rule_target.lower().startswith("print")


def test_parse_show_contested_maps_to_lost_margin() -> None:
    allow = AllowList(tuples=frozenset())
    result = parse_review_focus_deterministic("show contested", allow)
    assert result.ok
    assert result.filter.tbc_reason == "lost_margin"
    assert result.filter.active


def test_parse_show_not_contested_excludes_lost_margin() -> None:
    allow = AllowList(tuples=frozenset())
    result = parse_review_focus_deterministic("show not contested", allow)
    assert result.ok
    assert result.filter.tbc_reason == "!lost_margin"
    assert result.filter.active


def test_resolve_tbc_reason_alias_variants() -> None:
    from cs_tickets.tbc_filter_nl import resolve_tbc_reason_alias

    assert resolve_tbc_reason_alias("weak signal") == "below_threshold"
    assert resolve_tbc_reason_alias("no rules matched") == "zero_candidate"
    assert resolve_tbc_reason_alias("without match") == "zero_candidate"
    assert resolve_tbc_reason_alias("no matches") == "zero_candidate"
    assert resolve_tbc_reason_alias("unmatched") == "zero_candidate"
    assert resolve_tbc_reason_alias("rules blocked") == "allowlist_filtered"
    assert resolve_tbc_reason_alias("not contested") == "!lost_margin"
    assert resolve_tbc_reason_alias("gsdfsaf") == ""


def test_parse_without_match_tbc_is_zero_candidate_not_mismatch_categories() -> None:
    """'match' must not fuzzy-hit allow-list labels like Price Mismatch."""
    allow = AllowList(
        tuples=frozenset(
            {
                ("B2C", "Complaint", "Billing", "Offer vs Reality Mismatch", "N/A"),
                ("B2C", "Complaint", "Billing", "Price Mismatch", "N/A"),
                ("B2C", "Service Task", "Other", "TBC", "N/A"),
            }
        )
    )
    result = parse_review_focus_deterministic(
        "show tickets without match [tbc]",
        allow,
    )
    assert result.ok
    assert result.filter.tbc_reason == "zero_candidate"
    assert result.filter.categories == ()
    assert "mismatch" not in " ".join(result.filter.categories).lower()


def test_parse_b2c_category_list() -> None:
    allow = AllowList(
        tuples=frozenset(
            {
                ("B2C", "Complaint", "Technical Bug", "Access Loop or App Bug", "N/A"),
                ("B2C", "Complaint", "Refund", "Cancellation Request", "N/A"),
            }
        )
    )
    result = parse_review_focus_deterministic(
        "now i want to review these categories under b2c 1. access loop and bug 2. cancellation",
        allow,
    )
    assert result.ok
    assert result.filter.tier1 == "B2C"
    joined = " ".join(result.filter.categories).lower()
    assert "access" in joined or "cancellation" in joined


def test_batch_rule_prefill_includes_focus_and_examples() -> None:
    filt = TbcQueueFilter(q="sherina", tier1="B2C", categories=("Print",))
    text = build_filter_batch_rule_prefill(
        filt,
        matched_count=5,
        sample_ticket_ids=("101", "102"),
        sample_quotes=("Sherina print issue", "Another sherina ticket"),
        rule_target="Print",
    )
    assert "sherina" in text.lower()
    assert "Print" in text
    assert "#101" in text
    assert "5 manual-review" in text
