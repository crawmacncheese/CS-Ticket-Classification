"""Consistency Gateway — validate proposals and grade risk before Confirm.

Skills/APIs emit proposals; this module grades them. It does **not** commit
live rules (Confirm remains the only write path — Model B).
"""

from __future__ import annotations

from typing import Any

# Risk grades (API + skill contracts)
RISK_OK = "ok"
RISK_WARN_SHIELD = "warn_shield"
RISK_WARN_CHURN = "warn_churn"
RISK_WARN_DUPLICATE = "warn_duplicate"
RISK_BLOCK_SCHEMA = "block_schema"

# Soft churn: many tier changes on a small result set looks aggressive
_CHURN_CHANGED_MIN = 5
_CHURN_CHANGED_RATIO = 0.4


def grade_compile_risk(
    *,
    errors: tuple[str, ...] | list[str] = (),
    warnings: tuple[str, ...] | list[str] = (),
) -> str:
    """Grade a compile proposal from validation errors + soft warnings."""
    if errors:
        return RISK_BLOCK_SCHEMA
    blob = " ".join(str(w) for w in warnings).lower()
    if "already exists" in blob or "duplicate" in blob:
        return RISK_WARN_DUPLICATE
    if (
        "shield" in blob
        or "overlap" in blob
        or "stefan" in blob
        or "floor" in blob
        or "precedence" in blob
    ):
        return RISK_WARN_SHIELD
    return RISK_OK


def grade_preview_risk(summary: dict[str, Any] | None) -> str:
    """Grade dry-run impact from summarize_preview_results() shape."""
    if not summary:
        return RISK_OK
    if int(summary.get("shield_overlap") or 0) > 0:
        return RISK_WARN_SHIELD
    changed = int(summary.get("changed") or 0)
    rows = int(summary.get("result_rows") or 0) or changed
    if changed >= _CHURN_CHANGED_MIN and rows > 0:
        if changed / rows >= _CHURN_CHANGED_RATIO or changed >= 10:
            return RISK_WARN_CHURN
    return RISK_OK


def attach_compile_risk(payload: dict[str, Any]) -> dict[str, Any]:
    """Mutate/return compile API dict with ``risk`` field."""
    payload["risk"] = grade_compile_risk(
        errors=payload.get("errors") or (),
        warnings=payload.get("warnings") or (),
    )
    return payload


def attach_preview_risk(summary: dict[str, Any]) -> dict[str, Any]:
    """Mutate/return preview summary with ``risk`` field."""
    summary = dict(summary)
    summary["risk"] = grade_preview_risk(summary)
    return summary
