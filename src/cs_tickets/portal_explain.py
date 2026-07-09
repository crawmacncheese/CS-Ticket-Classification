"""On-demand classification explanation for portal ticket preview."""

from __future__ import annotations

from typing import Any

from cs_tickets.classify import classify_row_with_explanation, portal_reason_bucket, tbc_reason
from cs_tickets.classifier_rules import RuleSpec
from cs_tickets.portal_classify_context import suggest_tier_for_prefill
from cs_tickets.portal_copy import TBC_REASON_LABELS
from cs_tickets.taxonomy import AllowList


def explain_ticket_payload(
    row: dict[str, Any],
    allow: AllowList,
    *,
    rule_specs: tuple[RuleSpec, ...] | None = None,
) -> dict[str, Any]:
    """JSON-serializable explanation for a single classified row."""
    decision = classify_row_with_explanation(row, allow, rule_specs=rule_specs)
    bucket = portal_reason_bucket(decision, output_row=row)
    payload = {
        "tier": list(decision.tier),
        "score": decision.score,
        "fallback_used": decision.fallback_used,
        "candidates": [
            {"tier": list(tier), "score": score}
            for tier, score in decision.candidates[:3]
        ],
        "evidence": [
            {
                "rule_id": ev.rule_id,
                "tier": list(ev.tier),
                "weight": ev.weight,
                "signal": ev.signal,
            }
            for ev in decision.evidence
        ],
        "tbc_reason": bucket if bucket != "not_tbc" else None,
        "tbc_reason_label": (
            TBC_REASON_LABELS.get(bucket, bucket) if bucket != "not_tbc" else None
        ),
        "tbc_reason_detail": tbc_reason(decision) if decision.fallback_used else None,
    }
    payload["suggested_tier"] = suggest_tier_for_prefill(payload)
    return payload
