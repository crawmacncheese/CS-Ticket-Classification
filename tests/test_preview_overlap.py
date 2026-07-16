"""Preview overlap report (Phase C.4)."""

from __future__ import annotations

from cs_tickets.classifier_rules import RuleSpec
from cs_tickets.portal_rules import preview_rule_on_rows, summarize_preview_results
from cs_tickets.taxonomy import AllowList


def _allow(*tiers: tuple[str, str, str, str, str]) -> AllowList:
    return AllowList(frozenset(tiers))


STEFAN_TIER = (
    "B2C",
    "Service Task",
    "Account Management",
    "Comments being block",
    "N/A",
)
REFUND_TIER = ("B2C", "Complaint", "Refund", "Refund Request", "N/A")
SYSTEM_TIER = ("B2C", "Service Task", "Billing & Admin", "System Report", "N/A")


def _stefan_rule() -> RuleSpec:
    return RuleSpec(
        id="stefan_rule_moderation",
        tier=STEFAN_TIER,
        weight=18.0,
        any_blob=("moderation", "deleted comment", "biased moderators"),
        override=True,
        display_name="Stefan Rule",
    )


def _refund_candidate() -> RuleSpec:
    return RuleSpec(
        id="candidate.refund.keyword.b2c",
        tier=REFUND_TIER,
        weight=12.0,
        any_blob=("refund",),
        override=False,
    )


def _refund_override_candidate() -> RuleSpec:
    """Lower id sorts after stefan — Stefan wins override contest when both match."""
    return RuleSpec(
        id="zz_candidate_refund_override",
        tier=REFUND_TIER,
        weight=18.0,
        any_blob=("refund", "moderation"),
        override=True,
    )


def test_preview_overlap_stefan_shield_vs_candidate() -> None:
    allow = _allow(STEFAN_TIER, REFUND_TIER, SYSTEM_TIER)
    stefan = _stefan_rule()
    candidate = _refund_override_candidate()
    rows = [
        {
            "id": "1",
            "subject": "Refund after moderation",
            "description": "Please refund. Also moderation deleted comment issue.",
            "tags": "[]",
        }
    ]
    results = preview_rule_on_rows(rows, allow, (stefan,), candidate, limit=10)
    assert len(results) == 1
    row = results[0]
    assert row["description"].startswith("Please refund")
    assert row["candidate_matched"] is True
    assert "stefan_rule_moderation" in row["shield_overlap"]
    assert "stefan_rule_moderation" in {e["rule_id"] for e in row["evidence_after"]}
    # Stefan wins override by id sort (stefan_ < zz_)
    assert row["candidate_won"] is False
    summary = summarize_preview_results(results)
    assert summary["shield_overlap"] == 1
    assert summary["shield_overlap_rules"].get("stefan_rule_moderation") == 1
    assert "overlap" in summary["headline"]


def test_preview_includes_matched_even_if_tier_unchanged() -> None:
    """Rosetta-style: already on System Report; candidate still matches (matchers fire)."""
    allow = _allow(SYSTEM_TIER, REFUND_TIER)
    live = (
        RuleSpec(
            id="billing.system_report.rosetta_live.b2c",
            tier=SYSTEM_TIER,
            weight=14.0,
            any_blob=("thanks. rosetta system email",),
        ),
    )
    candidate = RuleSpec(
        id="billing.system_report.rosetta_thanks.b2c",
        tier=SYSTEM_TIER,
        weight=14.0,
        any_blob=("thanks. rosetta system email",),
    )
    rows = [
        {
            "id": "170002",
            "subject": "Cancellation? (system email)",
            "description": "Thanks. Rosetta System Email",
            "tags": "[]",
        },
        {
            "id": "170001",
            "subject": "Please cancel",
            "description": "cancel my subscription",
            "tags": "[]",
        },
    ]
    results = preview_rule_on_rows(rows, allow, live, candidate, limit=10)
    ids = {r["ticket_id"] for r in results}
    assert "170002" in ids
    matched = next(r for r in results if r["ticket_id"] == "170002")
    assert matched["candidate_matched"] is True
    assert matched["tier_changed"] is False
    assert matched["candidate_won"] is False


def test_preview_candidate_wins_non_shield() -> None:
    allow = _allow(SYSTEM_TIER, REFUND_TIER)
    live: tuple[RuleSpec, ...] = ()
    candidate = RuleSpec(
        id="candidate.system_report.unique.b2c",
        tier=SYSTEM_TIER,
        weight=14.0,
        any_blob=("unique-xyzzy-system-token",),
    )
    rows = [
        {
            "id": "9",
            "subject": "Random question",
            "description": "Please note unique-xyzzy-system-token for routing.",
            "tags": "[]",
        }
    ]
    results = preview_rule_on_rows(rows, allow, live, candidate)
    assert results[0]["candidate_matched"] is True
    assert results[0]["candidate_won"] is True
    assert results[0]["tier_changed"] is True
    assert results[0]["shield_overlap"] == []
    summary = summarize_preview_results(results)
    assert summary["changed"] == 1
    assert summary["candidate_won"] == 1
