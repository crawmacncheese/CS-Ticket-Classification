"""TBC queue filters — Christine-style keyword + category focus batches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cs_tickets.classifier_rules import RuleSpec
from cs_tickets.portal_explain import explain_ticket_payload
from cs_tickets.schema import TIER_COLUMNS
from cs_tickets.taxonomy import AllowList


@dataclass(frozen=True)
class TbcQueueFilter:
    """Filter pending manual-review tickets before chunking."""

    q: str = ""
    tier1: str = ""
    categories: tuple[str, ...] = ()
    tbc_reason: str = ""

    @classmethod
    def from_query(
        cls,
        *,
        q: str | None = None,
        tier1: str | None = None,
        categories: str | None = None,
        tbc_reason: str | None = None,
    ) -> TbcQueueFilter:
        cats: list[str] = []
        if categories:
            cats = [c.strip() for c in categories.split(",") if c.strip()]
        return cls(
            q=(q or "").strip(),
            tier1=(tier1 or "").strip(),
            categories=tuple(cats),
            tbc_reason=(tbc_reason or "").strip(),
        )

    @property
    def active(self) -> bool:
        return bool(self.q or self.tier1 or self.categories or self.tbc_reason)

    def as_dict(self) -> dict[str, Any]:
        return {
            "q": self.q,
            "tier1": self.tier1,
            "categories": list(self.categories),
            "tbc_reason": self.tbc_reason,
            "active": self.active,
        }


def _row_search_blob(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("id") or ""),
        str(row.get("subject") or ""),
        str(row.get("description") or ""),
        str(row.get("tags") or ""),
        str(row.get("requester_email") or ""),
    ]
    return " ".join(parts).lower()


def _tier_path_label(tier: tuple[str, ...] | list[str], *, max_parts: int = 4) -> str:
    parts = [str(x) for x in tier[:max_parts] if str(x).strip()]
    return " → ".join(parts)


def _row_tier_paths(row: dict[str, Any], explain: dict[str, Any]) -> list[str]:
    assigned = tuple(str(row.get(col) or "") for col in TIER_COLUMNS)
    paths = [_tier_path_label(assigned).lower()]
    for cand in explain.get("candidates") or []:
        raw = cand.get("tier")
        if isinstance(raw, list) and raw:
            paths.append(_tier_path_label(raw).lower())
    suggested = str(explain.get("suggested_tier") or "")
    if suggested:
        paths.append(suggested.lower())
    return paths


def row_matches_tbc_filter(
    row: dict[str, Any],
    explain: dict[str, Any],
    filt: TbcQueueFilter,
) -> bool:
    if filt.q:
        q = str(filt.q).lower()
        blob = _row_search_blob(row)
        # Support NL keyword lists encoded as q="a|b" => match any.
        if "|" in q:
            tokens = [t for t in q.split("|") if t.strip()]
            if tokens and not any(t in blob for t in tokens):
                return False
        else:
            if q not in blob:
                return False
    if filt.tier1 and str(row.get("Tier1_Segment") or "") != filt.tier1:
        return False
    if filt.categories:
        haystack = " | ".join(_row_tier_paths(row, explain))
        if not any(cat.lower() in haystack for cat in filt.categories):
            return False
    if filt.tbc_reason:
        code = str(explain.get("tbc_reason") or "")
        want = filt.tbc_reason
        if want.startswith("!"):
            excluded = want[1:]
            if code == excluded:
                return False
        elif code != want:
            return False
    return True


def filter_pending_tbc_rows(
    pending: list[dict[str, Any]],
    allow: AllowList,
    rule_specs: tuple[RuleSpec, ...],
    filt: TbcQueueFilter,
    *,
    tbc_reasons: dict[str, str] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return (row, explain) pairs matching the filter."""
    if not filt.active:
        out: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for row in pending:
            explain = explain_ticket_payload(row, allow, rule_specs=rule_specs)
            out.append((row, explain))
        return out

    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in pending:
        explain = explain_ticket_payload(row, allow, rule_specs=rule_specs)
        if tbc_reasons:
            tid = str(row.get("id") or "")
            if tid in tbc_reasons and not explain.get("tbc_reason"):
                explain = dict(explain)
                explain["tbc_reason"] = tbc_reasons[tid]
        if row_matches_tbc_filter(row, explain, filt):
            matched.append((row, explain))
    return matched


def build_tbc_filter_facets(
    pending: list[dict[str, Any]],
    allow: AllowList,
    rule_specs: tuple[RuleSpec, ...],
    *,
    tbc_reasons: dict[str, str] | None = None,
    max_tier4: int = 24,
) -> dict[str, Any]:
    """Counts for filter chips (tier1, tier4, top candidate labels, reasons)."""
    from collections import Counter

    tier1_counts: Counter[str] = Counter()
    tier4_counts: Counter[str] = Counter()
    candidate_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for row in pending:
        explain = explain_ticket_payload(row, allow, rule_specs=rule_specs)
        tid = str(row.get("id") or "")
        reason = explain.get("tbc_reason") or (tbc_reasons or {}).get(tid)
        if reason:
            reason_counts[str(reason)] += 1
        t1 = str(row.get("Tier1_Segment") or "")
        if t1:
            tier1_counts[t1] += 1
        t4 = str(row.get("Tier4_Type") or "")
        if t4:
            tier4_counts[t4] += 1
        cands = explain.get("candidates") or []
        if cands:
            raw = cands[0].get("tier")
            if isinstance(raw, list) and len(raw) >= 4:
                candidate_counts[_tier_path_label(raw)] += 1

    def _items(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
        return [
            {"label": label, "count": count}
            for label, count in counter.most_common(limit)
        ]

    return {
        "tier1": _items(tier1_counts, 6),
        "tier4": _items(tier4_counts, max_tier4),
        "top_candidates": _items(candidate_counts, max_tier4),
        "tbc_reasons": _items(reason_counts, 12),
    }
