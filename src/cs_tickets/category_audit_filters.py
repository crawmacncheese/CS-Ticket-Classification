"""Category audit filters — classified-bucket slice matching (non-TBC by default)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from cs_tickets.schema import TIER_COLUMNS


def _is_manual_review_row(row: dict[str, Any]) -> bool:
    tier4 = str(row.get("Tier4_Type") or "").lower()
    return "tbc" in tier4


@dataclass(frozen=True)
class CategoryAuditFilter:
    """Filter classified tickets for category audit sessions."""

    q: str = ""
    tier1: str = ""
    categories: tuple[str, ...] = ()
    tier4: str = ""
    include_tbc: bool = False

    @classmethod
    def from_query(
        cls,
        *,
        q: str | None = None,
        tier1: str | None = None,
        categories: str | None = None,
        tier4: str | None = None,
        include_tbc: str | int | bool | None = None,
    ) -> CategoryAuditFilter:
        cats: list[str] = []
        if categories:
            cats = [c.strip() for c in categories.split(",") if c.strip()]
        inc = False
        if isinstance(include_tbc, bool):
            inc = include_tbc
        elif include_tbc is not None:
            inc = str(include_tbc).strip().lower() in ("1", "true", "yes")
        return cls(
            q=(q or "").strip(),
            tier1=(tier1 or "").strip(),
            categories=tuple(cats),
            tier4=(tier4 or "").strip(),
            include_tbc=inc,
        )

    @property
    def active(self) -> bool:
        return bool(self.q or self.tier1 or self.categories or self.tier4 or self.include_tbc)

    def as_dict(self) -> dict[str, Any]:
        return {
            "q": self.q,
            "tier1": self.tier1,
            "categories": list(self.categories),
            "tier4": self.tier4,
            "include_tbc": self.include_tbc,
            "active": self.active,
        }

    def slice_label(self) -> str:
        parts: list[str] = []
        if self.tier1:
            parts.append(self.tier1)
        if self.tier4:
            parts.append(self.tier4)
        elif self.categories:
            parts.extend(self.categories)
        return " · ".join(parts) if parts else "All classified categories"

    def to_query_string(self) -> str:
        params: dict[str, str] = {}
        if self.q:
            params["q"] = self.q
        if self.tier1:
            params["tier1"] = self.tier1
        if self.categories:
            params["categories"] = ",".join(self.categories)
        if self.tier4:
            params["tier4"] = self.tier4
        if self.include_tbc:
            params["include_tbc"] = "1"
        return urlencode(params)


def category_audit_url(run_id: str, filt: CategoryAuditFilter | None = None) -> str:
    base = f"/run/{run_id}/category_audit"
    if filt is None:
        return base
    qs = filt.to_query_string()
    return f"{base}?{qs}" if qs else base


def _row_search_blob(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("id") or ""),
        str(row.get("subject") or ""),
        str(row.get("description") or ""),
        str(row.get("tags") or ""),
        str(row.get("requester_email") or ""),
    ]
    return " ".join(parts).lower()


def _assigned_tier_path(row: dict[str, Any]) -> str:
    return " → ".join(str(row.get(col) or "") for col in TIER_COLUMNS[:4]).lower()


def row_matches_category_audit_filter(
    row: dict[str, Any],
    filt: CategoryAuditFilter,
) -> bool:
    if not filt.include_tbc and _is_manual_review_row(row):
        return False
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
    if filt.tier4 and str(row.get("Tier4_Type") or "") != filt.tier4:
        return False
    if filt.categories:
        haystack = _assigned_tier_path(row)
        if not any(cat.lower() in haystack for cat in filt.categories):
            return False
    return True


def filter_category_audit_rows(
    rows: list[dict[str, Any]],
    filt: CategoryAuditFilter,
) -> list[dict[str, Any]]:
    return [row for row in rows if row_matches_category_audit_filter(row, filt)]


def category_audit_slice_stats(
    all_rows: list[dict[str, Any]],
    slice_rows: list[dict[str, Any]],
    filt: CategoryAuditFilter,
) -> dict[str, Any]:
    classified_total = sum(
        1 for row in all_rows if filt.include_tbc or not _is_manual_review_row(row)
    )
    return {
        "total_in_run": len(all_rows),
        "classified_in_run": classified_total,
        "total_in_slice": len(slice_rows),
        "slice_label": filt.slice_label(),
        "filter_active": filt.active,
    }
