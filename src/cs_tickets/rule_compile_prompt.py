"""System prompt assembly for rule_compile."""

from __future__ import annotations

from cs_tickets.classifier_rules import RuleSpec, rule_spec_to_json
from cs_tickets.rule_compile_corpus import (
    DEFAULT_CORPUS,
    format_disambiguation_for_prompt,
    format_few_shots_for_prompt,
)
from cs_tickets.taxonomy import AllowList

RULE_SPEC_FIELD_DOCS = """\
RuleSpec JSON fields (use only these matchers):
- id: stable snake_case identifier (prefix explicit.)
- tier: 5-item list [Tier1, Tier2, Tier3, Tier4, Granular] — must exist in allow-list
- weight: float 8–14 normal; shields ≥16–20 with override
- override: true when user says always/CRITICAL/even if refund/shield rule
- any_tags, all_tags: lowercase tag tokens
- any_subject, any_blob, exclude_blob, any_url: lowercase substrings
- any_requester: full lowercase email; any_requester_domain: domain after @
- requires_b2b_print_context: bool
- display_name, notes: optional strings
"""


def live_rules_digest(rules: tuple[RuleSpec, ...], *, limit: int = 40) -> str:
    lines = ["## Live rules (do not duplicate ids)", ""]
    for rule in rules[:limit]:
        matchers: list[str] = []
        if rule.any_blob:
            matchers.append(f"blob:{','.join(rule.any_blob[:3])}")
        if rule.any_subject:
            matchers.append(f"subject:{','.join(rule.any_subject[:2])}")
        if rule.any_tags:
            matchers.append(f"tags:{','.join(rule.any_tags[:3])}")
        if rule.any_requester_domain:
            matchers.append(f"domain:{','.join(rule.any_requester_domain[:2])}")
        flag = " override" if rule.override else ""
        path = " > ".join(rule.tier[:4])
        lines.append(f"- {rule.id}{flag}: {path} ({'; '.join(matchers) or 'see rule'})")
    if len(rules) > limit:
        lines.append(f"- … and {len(rules) - limit} more")
    return "\n".join(lines)


def allowlist_tier_index(allow: AllowList, *, max_tier4: int = 120) -> str:
    """Compact tier4 index for compile prompt."""
    by_t4: dict[str, list[tuple[str, str, str, str, str]]] = {}
    for tup in sorted(allow.tuples):
        key = tup[3].lower()
        by_t4.setdefault(key, []).append(tup)
    lines = ["## Allow-list tier4 index (full 5-tuple required in output)", ""]
    for t4 in sorted(by_t4.keys())[:max_tier4]:
        tuples = by_t4[t4]
        if len(tuples) == 1:
            lines.append(f"- {t4}: {list(tuples[0])}")
        else:
            lines.append(f"- {t4}: ({len(tuples)} paths — pick matching Tier1)")
            for tup in tuples[:3]:
                lines.append(f"    - {list(tup)}")
    return "\n".join(lines)


def build_compile_system_prompt(
    allow: AllowList,
    live_rules: tuple[RuleSpec, ...],
    *,
    user_message: str = "",
    taxonomy_excerpt: str | None = None,
) -> str:
    corpus = DEFAULT_CORPUS
    parts = [
        "You compile natural-language routing rules into strict JSON for a ticket classifier.",
        "Output ONLY a JSON object: "
        '{"rule": {...RuleSpec fields...}, "rationale": "...", "warnings": []}',
        RULE_SPEC_FIELD_DOCS,
        corpus.precedence,
        format_few_shots_for_prompt(corpus.few_shots),
        format_disambiguation_for_prompt(corpus.disambiguation),
        live_rules_digest(live_rules),
        allowlist_tier_index(allow),
    ]
    if taxonomy_excerpt:
        parts.append(taxonomy_excerpt)
    else:
        # Lazy default: load scoped taxonomy when message provided
        try:
            from cs_tickets.taxonomy_requirements import (
                format_taxonomy_for_compile,
                infer_scope_from_message,
                load_taxonomy_requirements,
            )

            tax = load_taxonomy_requirements()
            cats, sweeps = infer_scope_from_message(user_message)
            scoped = tax.sections_for_scope(
                categories=cats,
                sweep_ids=sweeps,
                text_hints=user_message,
            )
            parts.append(
                format_taxonomy_for_compile(tax, scoped=scoped, live_rules=live_rules)
            )
        except OSError:
            pass
    parts.extend(
        [
            "Never invent tiers outside the allow-list. Workbook 5-tuple wins over Gem 4-tier labels.",
            "When the exemplar is manual-review (TBC), the assigned tier is a fallback — "
            "compile the rule toward the category implied by ticket content, never toward TBC.",
            "Respect Global precedence shields; do not draft a normal-weight rule that fights Stefan / live-chat shields without override.",
        ]
    )
    return "\n\n".join(parts)


def build_compile_user_context(
    *,
    exemplar_row: dict | None = None,
    explain_payload: dict | None = None,
    prior_rule: RuleSpec | None = None,
) -> str:
    parts: list[str] = []
    if prior_rule is not None:
        parts.append("Prior compiled rule (refine this):")
        parts.append(str(rule_spec_to_json(prior_rule)))
    if exemplar_row:
        parts.append("Exemplar ticket:")
        parts.append(
            f"  id: {exemplar_row.get('id')}\n"
            f"  subject: {exemplar_row.get('subject')}\n"
            f"  requester: {exemplar_row.get('requester_email', '')}\n"
            f"  tags: {exemplar_row.get('tags')}\n"
            f"  description: {str(exemplar_row.get('description') or '')[:400]}"
        )
    if explain_payload:
        parts.append("Classifier explain:")
        if explain_payload.get("fallback_used"):
            parts.append(
                "  IMPORTANT: Current tier is manual-review FALLBACK only. "
                "Choose the rule target tier from ticket content — never TBC / manual review."
            )
        parts.append(f"  assigned_tier: {explain_payload.get('tier')}")
        parts.append(
            f"  tbc_reason: {explain_payload.get('tbc_reason_label') or explain_payload.get('tbc_reason')}"
        )
        if explain_payload.get("suggested_tier"):
            parts.append(f"  suggested_target: {explain_payload.get('suggested_tier')}")
        ev = explain_payload.get("evidence") or []
        if ev:
            parts.append(f"  rules_fired: {', '.join(str(e.get('rule_id') or '') for e in ev[:3])}")
        else:
            parts.append("  rules_fired: none — infer matchers from subject/description/tags.")
        candidates = explain_payload.get("candidates") or []
        if candidates and explain_payload.get("fallback_used"):
            top = candidates[0]
            parts.append(
                f"  top_candidate_rejected: {top.get('tier')} (score {top.get('score')})"
            )
    return "\n".join(parts)
