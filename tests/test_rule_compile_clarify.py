"""Compile clarify / retry / post-compile warning tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from cs_tickets.classifier_rules import RuleSpec
from cs_tickets.rule_compile import (
    compile_result_to_api_dict,
    compile_rule_message,
    human_compile_clarify,
    post_compile_warnings,
)


def _allow(repo_root: Path):
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    from cs_tickets.taxonomy import load_allowlist

    return load_allowlist(tax, xlsx)


def test_empty_message_clarify(repo_root: Path) -> None:
    result = compile_rule_message("  ", allow=_allow(repo_root), live_rules=())
    assert result.errors
    assert result.clarify_message
    assert "describe" in result.clarify_message.lower()
    api = compile_result_to_api_dict(result)
    assert api["ok"] is False
    assert "clarify_message" in api


def test_human_clarify_tier_error_is_plain() -> None:
    msg = human_compile_clarify(("tier path not on allow-list",), message="map x to y")
    assert "category path" in msg.lower()


def test_post_compile_warnings_low_shield_weight() -> None:
    rule = RuleSpec(
        id="junk.vendor.pitch",
        tier=("B2C", "Junk", "External", "PR Pitch", "N/A"),
        weight=10.0,
        override=True,
        any_blob=("press release",),
    )
    live = (
        RuleSpec(
            id="stefan.rule",
            tier=("B2C", "Account Management", "Comments", "Comments being block", "N/A"),
            weight=18.0,
            override=True,
            any_blob=("press release", "moderator"),
        ),
    )
    warns = post_compile_warnings(rule, live)
    assert any("floor" in w.lower() or "overlap" in w.lower() for w in warns)


def test_llm_retry_then_clarify(repo_root: Path, monkeypatch) -> None:
    monkeypatch.setenv("RULE_COMPILE_PROVIDER", "gemini")
    monkeypatch.setenv("RULE_COMPILE_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY_INTERNATIONAL", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    bad_payload = {
        "rule": {
            "id": "explicit.bad.tier",
            "tier": ["B2C", "Nope", "Nope", "Nope", "N/A"],
            "weight": 10.0,
            "any_blob": ["zzz"],
        },
        "rationale": "bad",
        "warnings": [],
    }

    with patch("cs_tickets.rule_compile._call_compile_llm", return_value=bad_payload):
        result = compile_rule_message(
            'Map "zzz token" to Billing & Admin > System Report.',
            allow=_allow(repo_root),
            live_rules=(),
            max_retries=2,
        )

    assert result.errors
    assert result.clarify_message
    assert result.attempts >= 2
    lowered = result.clarify_message.lower()
    assert "category" in lowered or "path" in lowered
