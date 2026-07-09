"""System prompt for TBC category suggestion (compile-only LLM, not /run)."""

from __future__ import annotations

from cs_tickets.rule_compile_corpus import DEFAULT_CORPUS, format_disambiguation_for_prompt
from cs_tickets.rule_compile_prompt import allowlist_tier_index
from cs_tickets.taxonomy import AllowList


def build_category_suggest_system_prompt(allow: AllowList) -> str:
    return "\n\n".join(
        [
            "You suggest a single support-ticket category for human review of manual-review (TBC) tickets.",
            "Output ONLY JSON:",
            '{"tier": [Tier1, Tier2, Tier3, Tier4, Granular], "rationale": "...", "confidence": "low|medium|high"}',
            "Rules:",
            "- Pick exactly ONE 5-tuple from the allow-list below.",
            "- NEVER output manual review / TBC tiers.",
            "- Use ticket subject, description, tags, and requester — not the classifier fallback.",
            "- Prefer Complaint vs Service Task using client patterns (dissatisfaction vs how-to).",
            "- Shield patterns: live-chat auto-trigger, moderation/Stefan, external junk/PR.",
            DEFAULT_CORPUS.precedence,
            format_disambiguation_for_prompt(DEFAULT_CORPUS.disambiguation),
            allowlist_tier_index(allow, max_tier4=80),
        ]
    )


def build_category_suggest_user_prompt(
    *,
    row: dict,
    explain_payload: dict | None = None,
) -> str:
    parts = [
        "Suggest the category a human analyst would assign:",
        f"  id: {row.get('id')}",
        f"  subject: {row.get('subject')}",
        f"  requester: {row.get('requester_email', '')}",
        f"  tags: {row.get('tags')}",
        f"  description: {str(row.get('description') or '')[:800]}",
    ]
    if explain_payload:
        parts.append("Classifier context (fallback assignment — do NOT copy as target):")
        parts.append(f"  assigned_tier: {explain_payload.get('tier')}")
        parts.append(
            f"  tbc_reason: {explain_payload.get('tbc_reason_label') or explain_payload.get('tbc_reason')}"
        )
        ev = explain_payload.get("evidence") or []
        if ev:
            parts.append(f"  rules_fired: {', '.join(str(e.get('rule_id') or '') for e in ev[:3])}")
        else:
            parts.append("  rules_fired: none")
        if explain_payload.get("suggested_tier"):
            parts.append(f"  classifier_hint: {explain_payload.get('suggested_tier')}")
    return "\n".join(parts)
