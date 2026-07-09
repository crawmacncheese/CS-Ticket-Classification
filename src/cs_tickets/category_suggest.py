"""LLM category suggestion for TBC review (not used on /run hot path)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cs_tickets.category_suggest_prompt import (
    build_category_suggest_system_prompt,
    build_category_suggest_user_prompt,
)
from cs_tickets.classifier_rules import RuleSpec, TierTuple
from cs_tickets.portal_classify_context import (
    build_tbc_rule_prefill,
    suggest_tier_for_prefill,
)
from cs_tickets.rule_compile import (
    CompileError,
    call_compile_llm_json,
    compile_llm_configured,
    resolve_tier_from_text,
)
from cs_tickets.taxonomy import AllowList, AllowlistRejectionInfo, classify_allowlist_rejection

_MAX_TBC_LLM_RETRIES = 3


@dataclass(frozen=True)
class CategorySuggestResult:
    ok: bool
    source: str  # llm | classifier | none
    tier: TierTuple | None
    tier_path: str
    rationale: str
    confidence: str
    prefill: str
    classifier_hint: str
    errors: tuple[str, ...]
    allowlist_rejection: AllowlistRejectionInfo | None = None


def _is_tbc_tier(tier: TierTuple) -> bool:
    return "tbc" in tier[3].lower()


def _tier_path(tier: TierTuple) -> str:
    return " → ".join(tier[:4])


def _classifier_tier_from_explain(
    explain: dict[str, Any],
    allow: AllowList,
) -> TierTuple | None:
    if explain.get("fallback_used"):
        candidates = explain.get("candidates") or []
        if candidates:
            raw = candidates[0].get("tier")
            if isinstance(raw, list) and len(raw) == 5:
                tup = tuple(str(x) for x in raw)
                if tup in allow.tuples and not _is_tbc_tier(tup):
                    return tup
        return None
    raw = explain.get("tier")
    if isinstance(raw, list) and len(raw) == 5:
        tup = tuple(str(x) for x in raw)
        if tup in allow.tuples and not _is_tbc_tier(tup):
            return tup
    return None


def _parse_suggest_response(
    raw: dict[str, Any],
    allow: AllowList,
    *,
    taxonomy_csv: Path | None = None,
) -> tuple[TierTuple | None, str, str, tuple[str, ...], AllowlistRejectionInfo | None, bool]:
    errors: list[str] = []
    rejection: AllowlistRejectionInfo | None = None
    tbc_rejected = False
    rationale = str(raw.get("rationale") or "").strip()
    confidence = str(raw.get("confidence") or "medium").strip().lower()
    if confidence not in ("low", "medium", "high"):
        confidence = "medium"

    tier_raw = raw.get("tier")
    tier: TierTuple | None = None
    if isinstance(tier_raw, list) and len(tier_raw) == 5:
        candidate = tuple(str(x) for x in tier_raw)
        if candidate in allow.tuples:
            if _is_tbc_tier(candidate):
                errors.append("Model suggested manual review / TBC — rejected.")
                tbc_rejected = True
            else:
                tier = candidate
        else:
            rejection = classify_allowlist_rejection(candidate, allow, taxonomy_csv)
            errors.append(rejection.message)
    else:
        text = str(raw.get("tier_path") or raw.get("category") or "")
        if text:
            tier = resolve_tier_from_text(text, allow)
            if tier and _is_tbc_tier(tier):
                tier = None
                errors.append("Resolved tier was manual review / TBC — rejected.")
                tbc_rejected = True
            elif tier is None:
                errors.append(f"Could not resolve category: {text[:80]}")
        else:
            errors.append("Model response missing tier.")

    return tier, rationale, confidence, tuple(errors), rejection, tbc_rejected


def suggest_category_for_ticket(
    row: dict[str, Any],
    allow: AllowList,
    *,
    explain_payload: dict[str, Any] | None = None,
    live_rules: tuple[RuleSpec, ...] = (),
    use_llm: bool = True,
    taxonomy_csv: Path | None = None,
) -> CategorySuggestResult:
    """Suggest category for one TBC ticket. LLM when configured; else classifier hint only."""
    explain = explain_payload or {}
    classifier_hint = suggest_tier_for_prefill(explain)
    classifier_tier = _classifier_tier_from_explain(explain, allow)
    ticket_id = str(row.get("id") or "")

    def _result(
        *,
        ok: bool,
        source: str,
        tier: TierTuple | None,
        rationale: str,
        confidence: str,
        errors: tuple[str, ...] = (),
        allowlist_rejection: AllowlistRejectionInfo | None = None,
    ) -> CategorySuggestResult:
        prefill_explain = dict(explain)
        if tier:
            prefill_explain["suggested_tier"] = _tier_path(tier)
        return CategorySuggestResult(
            ok=ok,
            source=source,
            tier=tier,
            tier_path=_tier_path(tier) if tier else "",
            rationale=rationale,
            confidence=confidence,
            prefill=build_tbc_rule_prefill(
                ticket_id=ticket_id,
                row=row,
                explain=prefill_explain,
            ),
            classifier_hint=classifier_hint,
            errors=errors,
            allowlist_rejection=allowlist_rejection,
        )

    if not use_llm or not compile_llm_configured():
        if classifier_tier:
            return _result(
                ok=True,
                source="classifier",
                tier=classifier_tier,
                rationale="Top classifier candidate (deterministic, below confidence gate).",
                confidence="low",
            )
        return _result(
            ok=False,
            source="none",
            tier=None,
            rationale="",
            confidence="low",
            errors=(
                "AI suggestion unavailable (configure RULE_COMPILE API key). "
                "Use ticket content to pick a category.",
            ),
        )

    system = build_category_suggest_system_prompt(allow)
    user = build_category_suggest_user_prompt(row=row, explain_payload=explain)
    try:
        tier: TierTuple | None = None
        rationale = ""
        confidence = "medium"
        errors: tuple[str, ...] = ()
        rejection: AllowlistRejectionInfo | None = None
        for attempt in range(_MAX_TBC_LLM_RETRIES):
            raw = call_compile_llm_json(system, user)
            tier, rationale, confidence, errors, rejection, tbc_rejected = _parse_suggest_response(
                raw,
                allow,
                taxonomy_csv=taxonomy_csv,
            )
            if tier or not tbc_rejected:
                break
            if attempt + 1 < _MAX_TBC_LLM_RETRIES:
                errors = errors + (f"Retrying ({attempt + 2}/{_MAX_TBC_LLM_RETRIES})…",)
        if tier:
            return _result(
                ok=True,
                source="llm",
                tier=tier,
                rationale=rationale or "AI suggestion from ticket content.",
                confidence=confidence,
                errors=errors,
                allowlist_rejection=rejection,
            )
        if classifier_tier:
            return _result(
                ok=True,
                source="classifier",
                tier=classifier_tier,
                rationale=(
                    rationale
                    or "AI could not validate a tier; showing classifier top candidate."
                ),
                confidence="low",
                errors=errors,
                allowlist_rejection=rejection,
            )
        return _result(
            ok=False,
            source="none",
            tier=None,
            rationale=rationale,
            confidence="low",
            errors=errors or ("Could not suggest a category.",),
            allowlist_rejection=rejection,
        )
    except (CompileError, json.JSONDecodeError, ValueError, KeyError) as exc:
        if classifier_tier:
            return _result(
                ok=True,
                source="classifier",
                tier=classifier_tier,
                rationale=f"AI unavailable ({exc}); classifier top candidate shown.",
                confidence="low",
                errors=(str(exc),),
            )
        return _result(
            ok=False,
            source="none",
            tier=None,
            rationale="",
            confidence="low",
            errors=(str(exc),),
        )


def suggest_result_to_api_dict(result: CategorySuggestResult) -> dict[str, Any]:
    rejection = result.allowlist_rejection
    return {
        "ok": result.ok,
        "source": result.source,
        "tier": list(result.tier) if result.tier else None,
        "tier_path": result.tier_path,
        "rationale": result.rationale,
        "confidence": result.confidence,
        "prefill": result.prefill,
        "classifier_hint": result.classifier_hint,
        "errors": list(result.errors),
        "allowlist_rejection": (
            {
                "cause": rejection.cause,
                "message": rejection.message,
                "rejected_tier": list(rejection.rejected_tier) if rejection.rejected_tier else None,
                "rejected_path": rejection.rejected_path,
                "close_match_tier": (
                    list(rejection.close_match_tier) if rejection.close_match_tier else None
                ),
                "close_match_path": rejection.close_match_path,
                "can_add_to_allowlist": rejection.can_add_to_allowlist,
                "novelty_type": rejection.novelty_type,
            }
            if rejection
            else None
        ),
    }
