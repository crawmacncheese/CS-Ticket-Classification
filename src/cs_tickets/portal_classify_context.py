"""Shared classify explain + TBC prefill helpers (no portal route imports)."""

from __future__ import annotations

from typing import Any

from cs_tickets.portal_copy import TBC_REASON_LABELS
from cs_tickets.rule_compile_corpus import TBC_COMPILE_PREFILL_TEMPLATE

QUOTE_LIMIT = 120


def quote_snippet(row: dict[str, Any], *, limit: int = QUOTE_LIMIT) -> str:
    subject = str(row.get("subject") or row.get("raw_subject") or "").strip()
    body = str(row.get("description") or "").strip()
    if body:
        body = " ".join(body.split())
    if subject and body:
        combined = f"{subject} — {body}"
    else:
        combined = subject or body
    if len(combined) > limit:
        return combined[: limit - 1] + "…"
    return combined


def _tier_path(tier: list[str] | tuple[str, ...] | None) -> str:
    if not tier:
        return ""
    return " → ".join(tier[:4])


def _is_tbc_tier_path(path: str) -> bool:
    return "tbc" in path.lower()


def suggest_tier_for_prefill(explain: dict[str, Any]) -> str:
    """Human-facing category hint for TBC review — never anchor on fallback TBC."""
    if explain.get("fallback_used"):
        candidates = explain.get("candidates") or []
        if candidates:
            top = _tier_path(candidates[0].get("tier"))
            score = candidates[0].get("score")
            if top and not _is_tbc_tier_path(top):
                score_note = f", score {score}" if score is not None else ""
                return f"{top} (top candidate{score_note}, below confidence gate)"
        return "infer from ticket content (no rule match)"
    path = _tier_path(explain.get("tier"))
    if path and not _is_tbc_tier_path(path):
        return path
    return "infer from ticket content"


def suggested_tier_label(explain: dict[str, Any]) -> str:
    """Queue table column — same semantics as prefill hint."""
    hint = suggest_tier_for_prefill(explain)
    if hint.startswith("infer from ticket content"):
        return "No rule match — infer from content"
    return hint


def why_tbc_label(explain: dict[str, Any], *, tbc_reason_code: str | None = None) -> str:
    code = explain.get("tbc_reason") or tbc_reason_code
    if code and code != "not_tbc":
        label = TBC_REASON_LABELS.get(str(code), str(code))
        detail = explain.get("tbc_reason_detail")
        if detail and detail != code:
            return f"{label}: {detail}"
        return label
    detail = explain.get("tbc_reason_detail")
    return str(detail or "Needs manual review")


def classifier_note_for_prefill(explain: dict[str, Any]) -> str:
    evidence = explain.get("evidence") or []
    if evidence:
        ids = ", ".join(str(ev.get("rule_id") or "") for ev in evidence[:3])
        return f"Rules that fired: {ids}."
    candidates = explain.get("candidates") or []
    if candidates and explain.get("fallback_used"):
        top = _tier_path(candidates[0].get("tier"))
        if top:
            return f"No rule met confidence threshold. Top candidate: {top}."
    return "No classification rules matched this ticket."


def build_tbc_rule_prefill(
    *,
    ticket_id: str,
    row: dict[str, Any],
    explain: dict[str, Any],
) -> str:
    """Christine-style compile chat seed — anchored on ticket content, not TBC fallback."""
    subject = str(row.get("subject") or "")[:80]
    quote = quote_snippet(row, limit=200)
    why = why_tbc_label(explain)
    note = classifier_note_for_prefill(explain)
    explicit = str(explain.get("suggested_tier") or "").strip()
    target = explicit if explicit and not explicit.startswith("infer from") else suggest_tier_for_prefill(explain)
    target_line = (
        f"Suggested target: {target}."
        if not str(target).startswith("infer from")
        else "Pick the category a human would use from the ticket content (not manual review / TBC)."
    )
    return TBC_COMPILE_PREFILL_TEMPLATE.format(
        ticket_id=ticket_id,
        subject_snippet=subject,
        quote_snippet=quote,
        why_tbc=why,
        classifier_note=note,
        target_line=target_line,
    ).strip()
