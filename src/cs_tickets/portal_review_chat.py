"""Run-scoped review chat orchestration (Phase E) — deterministic profile turns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cs_tickets.session_md import append_execution_log
from cs_tickets.session_metadata import resolve_sweep_id
from cs_tickets.session_profile import SessionProfile, build_session_profile
from cs_tickets.taxonomy import AllowList
from cs_tickets.taxonomy_requirements import (
    load_taxonomy_requirements,
    TaxonomyRequirements,
)

# Portal sweep id → taxonomy sweep_id used in docs/taxonomy-requirements.md
_TAXONOMY_SWEEP_FOR_PORTAL: dict[str, str] = {
    "rosetta_system_email": "rosetta_footer",
}


def _compile_phrase_for_sweep(
    tax: TaxonomyRequirements | None,
    portal_sweep_id: str,
) -> str | None:
    if tax is None:
        return None
    candidates = {portal_sweep_id.lower()}
    mapped = _TAXONOMY_SWEEP_FOR_PORTAL.get(portal_sweep_id)
    if mapped:
        candidates.add(mapped.lower())
    candidates.add(resolve_sweep_id(portal_sweep_id).lower())
    for sec in tax.sections:
        sec_ids = {s.lower() for s in sec.sweep_ids}
        if sec_ids.intersection(candidates) and sec.compile_phrases:
            return sec.compile_phrases[0]
    return None


def format_focus_parse_summary(
    workbench_filter: dict[str, Any] | None,
    *,
    parse_source: str = "",
    parse_rationale: str = "",
) -> str:
    """Human-readable interpretation of the structured focus for chat."""
    from cs_tickets.tbc_filter_nl import tbc_reason_filter_label

    filt = workbench_filter or {}
    clauses: list[str] = []

    tier1 = str(filt.get("tier1") or "").strip()
    if tier1:
        clauses.append(f"the {tier1} segment")

    q = str(filt.get("q") or "").strip()
    if q:
        if "|" in q:
            tokens = [t.strip() for t in q.split("|") if t.strip()]
            if len(tokens) >= 2:
                clauses.append(
                    "tickets mentioning "
                    + ", ".join(f"“{t}”" for t in tokens[:-1])
                    + f", or “{tokens[-1]}”"
                )
            elif tokens:
                clauses.append(f"tickets mentioning “{tokens[0]}”")
        else:
            clauses.append(f"tickets mentioning “{q}”")

    cats = filt.get("categories") or []
    if isinstance(cats, list) and cats:
        labels = [str(c).strip() for c in cats if str(c).strip()]
        if labels:
            if len(labels) == 1:
                clauses.append(f"category focus “{labels[0]}”")
            else:
                clauses.append(
                    "category focus "
                    + ", ".join(f"“{c}”" for c in labels[:-1])
                    + f", and “{labels[-1]}”"
                )

    reason = str(filt.get("tbc_reason") or "").strip()
    if reason:
        label = tbc_reason_filter_label(reason)
        if reason.startswith("!"):
            clauses.append(f"manual-review tickets except {label}")
        else:
            # label is already analyst language (e.g. Contested)
            clauses.append(f"{label} manual-review tickets only")

    target = str(filt.get("rule_target") or "").strip()
    if target:
        clauses.append(f"rule target “{target}”")

    if not clauses:
        understood = "Understood as: no specific table filter."
    elif len(clauses) == 1:
        understood = f"Understood as: {clauses[0]}."
    else:
        understood = (
            "Understood as: "
            + ", ".join(clauses[:-1])
            + f", and {clauses[-1]}."
        )

    lines = [understood]
    src = (parse_source or "").strip().lower()
    if src == "deterministic":
        lines.append("Matched from known review phrases.")
    elif src == "llm":
        lines.append("Interpreted with AI, then validated against filter fields.")
    # Skip raw rationale when it just restates machine parse output.
    rat = parse_rationale.strip()
    if rat and src == "llm" and not rat.lower().startswith("parsed focus:"):
        lines.append(rat)
    return "\n".join(lines)


def build_review_chat_turn(
    rows: list[dict[str, Any]],
    *,
    focus_nl: str,
    allow: AllowList,
    taxonomy: TaxonomyRequirements | None = None,
    tbc_reasons: dict[str, str] | None = None,
    use_llm: bool | None = None,
) -> dict[str, Any]:
    """Profile turn → cards for the /rules chat UI.

    Focus parse: LLM-first when configured (``prefer_llm``), else deterministic
    aliases; validated structured filter only — never rule compile.
    """
    text = (focus_nl or "").strip()
    if not text:
        return {
            "ok": False,
            "mode": "audit",
            "profile": None,
            "workbench_filter": None,
            "cards": [
                {
                    "type": "clarify",
                    "message": (
                        "Enter a review focus (e.g. review B2C, show contested), "
                        "open the TBC queue (“show all TBC”), or a compile phrase."
                    ),
                }
            ],
            "suggested_compile": None,
            "errors": ["text required"],
        }

    tax = taxonomy
    if tax is None:
        try:
            tax = load_taxonomy_requirements()
        except OSError:
            tax = None

    if use_llm is None:
        from cs_tickets.rule_compile import compile_llm_configured

        use_llm = compile_llm_configured()

    profile = build_session_profile(
        rows,
        text,
        allow,
        use_llm=bool(use_llm),
        prefer_llm=bool(use_llm),
        tbc_reasons=tbc_reasons,
    )

    # Unparsed / refused focus → clarify only (do not apply empty "whole run" slice)
    if not profile.parse_ok:
        msg = (
            (profile.parse_errors[0] if profile.parse_errors else "")
            or "I’m not sure what focus you mean. Try “review B2C”, “show contested”, "
            "“show all TBC”, or a Map/compile phrase."
        )
        return {
            "ok": False,
            "mode": "audit",
            "profile": profile.as_dict(),
            "workbench_filter": None,
            "cards": [{"type": "clarify", "message": msg}],
            "suggested_compile": None,
            "errors": list(profile.parse_errors),
            "headline": None,
        }

    workbench_filter = profile.workbench_filter()
    parse_summary = format_focus_parse_summary(
        workbench_filter,
        parse_source=profile.parse_source,
        parse_rationale=profile.parse_rationale,
    )
    cards: list[dict[str, Any]] = [
        {
            "type": "profile_summary",
            "focus_nl": profile.focus_nl,
            "slice_count": profile.slice_count,
            "tbc_count": profile.tbc_count,
            "parse_ok": profile.parse_ok,
            "parse_source": profile.parse_source,
            "parse_rationale": profile.parse_rationale,
            "parse_summary": parse_summary,
            "no_op": profile.no_op,
            "blockers": list(profile.blockers),
            "audit_filter": profile.audit_filter,
            "workbench_filter": workbench_filter,
            "tbc_reason": profile.tbc_reason,
        }
    ]

    suggested: str | None = None
    nonzero = [s for s in profile.sweep_summaries if s.match_count > 0]
    for sweep in nonzero:
        phrase = _compile_phrase_for_sweep(tax, sweep.sweep_id)
        card: dict[str, Any] = {
            "type": "sweep",
            "sweep_id": sweep.sweep_id,
            "match_count": sweep.match_count,
            "sample_ids": list(sweep.sample_ids),
            "compile_phrase": phrase,
        }
        cards.append(card)
        if phrase and suggested is None:
            suggested = phrase

    if profile.no_op:
        cards.append(
            {
                "type": "clarify",
                "message": profile.clarify_message
                or "No matches for this focus. Try a different scope.",
            }
        )
        suggested = None

    return {
        "ok": True,
        "mode": "audit",
        "profile": profile.as_dict(),
        "workbench_filter": workbench_filter,
        "parse_summary": parse_summary,
        "cards": cards,
        "suggested_compile": suggested,
        "errors": list(profile.parse_errors),
    }


def append_review_chat_log(
    session_md: Path | str | None,
    *,
    action: str,
    result: str,
) -> dict[str, Any]:
    """Optionally append to session MD; always return a log_entry for the UI."""
    entry = {"action": action, "result": result}
    path_str = str(session_md or "").strip()
    if not path_str:
        return {"ok": True, "logged": False, "log_entry": entry}
    path = Path(path_str)
    if not path.is_file():
        return {
            "ok": False,
            "logged": False,
            "log_entry": entry,
            "errors": [f"session_md not found: {path}"],
        }
    step = append_execution_log(path, action=action, result=result)
    entry["step"] = step
    return {"ok": True, "logged": True, "log_entry": entry, "session_md": str(path)}


def profile_headline(profile: SessionProfile | dict[str, Any]) -> str:
    if isinstance(profile, SessionProfile):
        data = profile.as_dict()
    else:
        data = profile
    sweeps = data.get("sweep_summaries") or []
    hit = sum(1 for s in sweeps if int(s.get("match_count") or 0) > 0)
    reason = str(data.get("tbc_reason") or "").strip()
    if reason:
        from cs_tickets.tbc_filter_nl import tbc_reason_filter_label

        label = tbc_reason_filter_label(reason)
        return (
            f"Focus “{data.get('focus_nl') or ''}”: "
            f"{data.get('slice_count', 0)} {label} TBC tickets "
            f"({data.get('tbc_count', 0)} TBC in run)."
        )
    return (
        f"Focus “{data.get('focus_nl') or ''}”: "
        f"{data.get('slice_count', 0)} tickets in slice, "
        f"{hit} sweep(s) with matches, "
        f"{data.get('tbc_count', 0)} TBC in run."
    )
