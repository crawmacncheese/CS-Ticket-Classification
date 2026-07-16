"""Deterministic session profile for Christine orchestration (Phase A)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cs_tickets.category_audit_filters import CategoryAuditFilter
from cs_tickets.category_audit_sweeps import run_category_audit_sweeps
from cs_tickets.portal_category_audit import build_category_audit_context
from cs_tickets.run_metadata import count_tbc_rows
from cs_tickets.taxonomy import AllowList
from cs_tickets.tbc_filter_nl import parse_review_focus_nl


@dataclass(frozen=True)
class SweepSummary:
    sweep_id: str
    match_count: int
    sample_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sweep_id": self.sweep_id,
            "match_count": self.match_count,
            "sample_ids": list(self.sample_ids),
        }


@dataclass(frozen=True)
class SessionProfile:
    focus_nl: str
    audit_filter: dict[str, Any]
    slice_count: int
    tbc_count: int
    sweep_summaries: tuple[SweepSummary, ...]
    no_op: bool
    parse_ok: bool
    parse_source: str
    parse_errors: tuple[str, ...] = ()
    rule_target: str = ""
    tbc_reason: str = ""
    parse_rationale: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "focus_nl": self.focus_nl,
            "audit_filter": self.audit_filter,
            "slice_count": self.slice_count,
            "tbc_count": self.tbc_count,
            "sweep_summaries": [s.as_dict() for s in self.sweep_summaries],
            "no_op": self.no_op,
            "parse_ok": self.parse_ok,
            "parse_source": self.parse_source,
            "parse_errors": list(self.parse_errors),
            "rule_target": self.rule_target,
            "tbc_reason": self.tbc_reason,
            "parse_rationale": self.parse_rationale,
        }

    def workbench_filter(self) -> dict[str, Any]:
        """Structured focus for syncing the docked workbench table."""
        filt = self.audit_filter or {}
        cats = filt.get("categories") or []
        if not isinstance(cats, list):
            cats = list(cats) if cats else []
        tbc_reason = self.tbc_reason or ""
        active = bool(
            filt.get("active") or filt.get("q") or filt.get("tier1") or cats or tbc_reason
        )
        return {
            "q": str(filt.get("q") or ""),
            "tier1": str(filt.get("tier1") or ""),
            "categories": [str(c) for c in cats],
            "tbc_reason": tbc_reason,
            "active": active,
            "rule_target": self.rule_target or "",
        }

    @property
    def blockers(self) -> tuple[str, ...]:
        if self.no_op:
            return ("ZERO_MATCHES",)
        return ()

    @property
    def clarify_message(self) -> str | None:
        if not self.no_op:
            return None
        return (
            "No tickets match this focus and no slice checks found matches. "
            "Try narrowing or broadening scope (e.g. tier, category, or keyword)."
        )


def _audit_filter_from_parse(
    *,
    tier1: str,
    categories: tuple[str, ...],
    q: str,
) -> CategoryAuditFilter:
    return CategoryAuditFilter.from_query(
        tier1=tier1 or None,
        categories=",".join(categories) if categories else None,
        q=q or None,
    )


def _sweep_summaries_from_rows(
    slice_rows: list[dict[str, Any]],
    *,
    allow: AllowList | None,
    sample_cap: int,
) -> tuple[SweepSummary, ...]:
    sweeps = run_category_audit_sweeps(slice_rows, allow)
    out: list[SweepSummary] = []
    for sweep in sweeps:
        out.append(
            SweepSummary(
                sweep_id=sweep.id,
                match_count=sweep.match_count,
                sample_ids=tuple(sweep.matched_ids[:sample_cap]),
            )
        )
    return tuple(out)


def compute_no_op(*, slice_count: int, sweep_summaries: tuple[SweepSummary, ...]) -> bool:
    if slice_count > 0:
        return False
    return all(s.match_count == 0 for s in sweep_summaries)


def build_session_profile(
    rows: list[dict[str, Any]],
    focus_nl: str,
    allow: AllowList,
    *,
    use_llm: bool = False,
    prefer_llm: bool = False,
    sweep_sample_cap: int = 5,
    tbc_reasons: dict[str, str] | None = None,
) -> SessionProfile:
    """Build a session profile from classified run rows and NL focus.

    ``use_llm`` / ``prefer_llm`` control structured focus extraction only —
    never rule compile.
    """
    parsed = parse_review_focus_nl(
        focus_nl,
        allow,
        use_llm=use_llm,
        prefer_llm=prefer_llm,
    )
    filt = parsed.filter
    audit_filter = _audit_filter_from_parse(
        tier1=filt.tier1,
        categories=filt.categories,
        q=filt.q,
    )

    if not parsed.ok:
        return SessionProfile(
            focus_nl=focus_nl.strip(),
            audit_filter=audit_filter.as_dict(),
            slice_count=0,
            tbc_count=count_tbc_rows(rows),
            sweep_summaries=(),
            no_op=True,
            parse_ok=False,
            parse_source=parsed.source,
            parse_errors=tuple(parsed.errors),
            rule_target=parsed.rule_target,
            tbc_reason=filt.tbc_reason,
            parse_rationale=parsed.rationale,
        )

    # TBC-reason focus (e.g. "show contested" / "show not contested").
    if filt.tbc_reason and tbc_reasons is not None:
        want = filt.tbc_reason
        if want.startswith("!"):
            excluded = want[1:]
            matched_ids = {
                tid
                for tid, reason in tbc_reasons.items()
                if reason != "not_tbc" and reason != excluded
            }
        else:
            matched_ids = {
                tid
                for tid, reason in tbc_reasons.items()
                if reason == want
            }
        slice_rows = [r for r in rows if str(r.get("id") or "") in matched_ids]
        sweep_summaries: tuple[SweepSummary, ...] = ()
        slice_count = len(slice_rows)
        no_op = slice_count == 0
        return SessionProfile(
            focus_nl=focus_nl.strip(),
            audit_filter=audit_filter.as_dict(),
            slice_count=slice_count,
            tbc_count=count_tbc_rows(rows),
            sweep_summaries=sweep_summaries,
            no_op=no_op,
            parse_ok=parsed.ok,
            parse_source=parsed.source,
            parse_errors=tuple(parsed.errors),
            rule_target=parsed.rule_target,
            tbc_reason=filt.tbc_reason,
            parse_rationale=parsed.rationale,
        )

    slice_rows, _stats = build_category_audit_context(rows, audit_filter)
    sweep_summaries = _sweep_summaries_from_rows(
        slice_rows,
        allow=allow,
        sample_cap=sweep_sample_cap,
    )
    slice_count = len(slice_rows)
    no_op = compute_no_op(slice_count=slice_count, sweep_summaries=sweep_summaries)
    return SessionProfile(
        focus_nl=focus_nl.strip(),
        audit_filter=audit_filter.as_dict(),
        slice_count=slice_count,
        tbc_count=count_tbc_rows(rows),
        sweep_summaries=sweep_summaries,
        no_op=no_op,
        parse_ok=parsed.ok,
        parse_source=parsed.source,
        parse_errors=tuple(parsed.errors),
        rule_target=parsed.rule_target,
        tbc_reason=filt.tbc_reason,
        parse_rationale=parsed.rationale,
    )
