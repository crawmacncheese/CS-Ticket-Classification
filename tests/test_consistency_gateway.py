"""Consistency Gateway risk grading."""

from __future__ import annotations

from cs_tickets.consistency_gateway import (
    RISK_BLOCK_SCHEMA,
    RISK_OK,
    RISK_WARN_CHURN,
    RISK_WARN_DUPLICATE,
    RISK_WARN_SHIELD,
    attach_compile_risk,
    attach_preview_risk,
    grade_compile_risk,
    grade_preview_risk,
)
from cs_tickets.rule_compile import CompileResult, compile_result_to_api_dict


def test_grade_compile_block_on_errors() -> None:
    assert grade_compile_risk(errors=("Tier not in allow-list",)) == RISK_BLOCK_SCHEMA


def test_grade_compile_shield_warning() -> None:
    assert (
        grade_compile_risk(warnings=("May overlap live shield `stefan` — preview carefully.",))
        == RISK_WARN_SHIELD
    )


def test_grade_compile_duplicate() -> None:
    assert grade_compile_risk(warnings=("Rule id already exists: x",)) == RISK_WARN_DUPLICATE


def test_grade_compile_ok() -> None:
    assert grade_compile_risk(warnings=()) == RISK_OK


def test_grade_preview_shield() -> None:
    assert grade_preview_risk({"shield_overlap": 2, "changed": 1, "result_rows": 3}) == RISK_WARN_SHIELD


def test_grade_preview_churn() -> None:
    assert (
        grade_preview_risk({"shield_overlap": 0, "changed": 12, "result_rows": 20})
        == RISK_WARN_CHURN
    )


def test_compile_result_api_includes_risk() -> None:
    result = CompileResult(
        rule=None,
        rationale="",
        warnings=(),
        errors=("Tier not in allow-list: x",),
        clarify_message="clarify",
    )
    payload = compile_result_to_api_dict(result)
    assert payload["risk"] == RISK_BLOCK_SCHEMA
    assert payload["ok"] is False


def test_attach_preview_risk_idempotent_shape() -> None:
    summary = attach_preview_risk(
        {"result_rows": 1, "changed": 0, "candidate_matched": 1, "shield_overlap": 0, "headline": "x"}
    )
    assert summary["risk"] == RISK_OK
    assert "headline" in summary


def test_attach_compile_risk_ok() -> None:
    assert attach_compile_risk({"ok": True, "warnings": [], "errors": []})["risk"] == RISK_OK
