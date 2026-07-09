"""Tests for rule_compile (heuristic path — no API key)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cs_tickets.rule_compile import _compile_llm_settings, compile_rule_message


def test_heuristic_compile_stripe(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    from cs_tickets.taxonomy import load_allowlist

    allow = load_allowlist(tax, xlsx)
    result = compile_rule_message(
        'Update: Map "Stripe payment completed" to Billing & Admin > System Report.',
        allow=allow,
        live_rules=(),
    )
    assert not result.errors
    assert result.rule is not None
    assert result.rule.tier[3] == "System Report"
    assert "stripe payment completed" in result.rule.any_blob


def test_heuristic_compile_rosetta_not_cancel(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    from cs_tickets.taxonomy import load_allowlist

    allow = load_allowlist(tax, xlsx)
    result = compile_rule_message(
        "If it contains Rosetta System Email, that is system email — NOT cancellation request.",
        allow=allow,
        live_rules=(),
    )
    assert not result.errors
    assert result.rule is not None
    assert result.rule.tier[3] == "System Report"


def test_heuristic_compile_contains_mark_as_junk(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    from cs_tickets.taxonomy import load_allowlist

    allow = load_allowlist(tax, xlsx)
    result = compile_rule_message(
        "If the text contains claim gift, mark as junk",
        allow=allow,
        live_rules=(),
    )
    assert not result.errors, result.errors
    assert result.rule is not None
    assert result.rule.tier[0] == "B2C"
    assert result.rule.tier[1] == "Junk"
    assert "claim gift" in result.rule.any_blob


def test_compile_llm_settings_qwen(monkeypatch) -> None:
    monkeypatch.setenv("RULE_COMPILE_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY_INTERNATIONAL", "test-key")
    monkeypatch.delenv("RULE_COMPILE_MODEL", raising=False)
    monkeypatch.delenv("RULE_COMPILE_API_BASE", raising=False)
    provider, api_key, model, api_base = _compile_llm_settings()
    assert provider == "qwen"
    assert api_key == "test-key"
    assert model == "qwen-plus"
    assert api_base == "https://dashscope-intl.aliyuncs.com/compatible-mode"


def test_compile_llm_settings_deepseek(monkeypatch) -> None:
    monkeypatch.setenv("RULE_COMPILE_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("RULE_COMPILE_MODEL", raising=False)
    provider, api_key, model, api_base = _compile_llm_settings()
    assert provider == "deepseek"
    assert api_key == "test-key"
    assert model == "deepseek-chat"
    assert api_base == "https://api.deepseek.com"


def test_compile_rejects_empty_message(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    from cs_tickets.taxonomy import load_allowlist

    allow = load_allowlist(tax, xlsx)
    result = compile_rule_message("   ", allow=allow, live_rules=())
    assert result.errors
