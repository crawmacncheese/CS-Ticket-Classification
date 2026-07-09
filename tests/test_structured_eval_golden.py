"""Golden eval cases for structured outputs (offline, deterministic).

These tests act as a lightweight evaluation harness for the two places where
LLM assistance is used:
- NL review focus -> TbcQueueFilter (tbc_filter_nl.py)
- NL rule message -> RuleSpec (rule_compile.py) via heuristic compiler path

The goal is to ensure stable, executable structured outputs even when natural
language varies.
"""

from __future__ import annotations

import pytest

from cs_tickets.rule_compile import compile_rule_message
from cs_tickets.taxonomy import AllowList
from cs_tickets.tbc_filter_nl import parse_review_focus_deterministic


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "review B2C cancellation tickets contains stripe",
            {"tier1": "B2C", "q": "stripe", "cat_contains": ("cancellation",)},
        ),
        (
            "anything contains sherina needs to be move under Print",
            {"q": "sherina", "cat_contains": ("print",)},
        ),
        (
            "now i want to review these categories under b2c 1. access loop and bug 2. cancellation",
            {"tier1": "B2C", "cat_contains": ("access", "cancellation")},
        ),
    ],
)
def test_golden_tbc_review_focus_parsing(text: str, expected: dict) -> None:
    allow = AllowList(
        tuples=frozenset(
            {
                ("B2C", "Service Task", "Print", "Delivery", "N/A"),
                ("B2C", "Complaint", "Technical Bug", "Access Loop or App Bug", "N/A"),
                ("B2C", "Complaint", "Refund", "Cancellation Request", "N/A"),
            }
        )
    )

    result = parse_review_focus_deterministic(text, allow)
    assert result.ok

    if "tier1" in expected:
        assert result.filter.tier1 == expected["tier1"]
    if "q" in expected:
        assert result.filter.q.lower() == expected["q"]

    joined = " ".join(result.filter.categories).lower()
    for needle in expected.get("cat_contains", ()):
        assert needle in joined


def test_golden_rule_compile_map_to_system_report_offline() -> None:
    """A stable offline compile case: quoted phrase + map-to category path."""
    allow = AllowList(
        tuples=frozenset(
            {
                ("B2C", "Service Task", "Billing & Admin", "System Report", "N/A"),
                ("B2C", "Service Task", "Print", "Delivery", "N/A"),
                ("B2C", "Junk", "Junk", "Junk", "N/A"),
            }
        )
    )

    result = compile_rule_message(
        'Update: Map "Stripe payment completed" to Billing & Admin > System Report.',
        allow=allow,
        live_rules=(),
    )
    assert not result.errors, result.errors
    assert result.rule is not None
    assert result.rule.id.startswith("explicit.")
    assert result.rule.tier[3] == "System Report"
    assert "stripe payment completed" in result.rule.any_blob

