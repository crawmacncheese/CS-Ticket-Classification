"""General slice checks for category audit (hygiene only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from cs_tickets.category_audit_duplicates import DUPLICATE_SWEEP_ID, duplicate_groups, duplicate_matched_ids
from cs_tickets.taxonomy import AllowList

_MATCH_ID_CAP = 50
_WORD_RE = re.compile(r"[a-z0-9@._-]+", re.IGNORECASE)


def _row_blob_lower(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("subject", "description", "tags", "_thread_blob"):
        v = row.get(key)
        if v:
            parts.append(str(v))
    return " ".join(parts).lower()


def _match_ids_by_patterns(
    slice_rows: list[dict[str, Any]],
    *,
    patterns: tuple[str, ...],
) -> list[str]:
    compiled = tuple(re.compile(p, re.IGNORECASE) for p in patterns)
    out: list[str] = []
    for row in slice_rows:
        blob = _row_blob_lower(row)
        if any(rx.search(blob) for rx in compiled):
            tid = str(row.get("id") or "")
            if tid:
                out.append(tid)
    return out


def _simple_sweep(
    *,
    sweep_id: str,
    label: str,
    description: str,
    matched_ids: list[str],
    match_id_cap: int,
) -> SweepResult:
    ids = [i for i in matched_ids if i]
    return SweepResult(
        id=sweep_id,
        label=label,
        description=description,
        match_count=len(ids),
        matched_ids=tuple(ids[:match_id_cap]),
    )


@dataclass(frozen=True)
class SweepResult:
    id: str
    label: str
    description: str
    match_count: int
    matched_ids: tuple[str, ...]
    matched_groups: tuple[tuple[str, ...], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "match_count": self.match_count,
            "matched_ids": list(self.matched_ids),
        }
        if self.matched_groups:
            out["matched_groups"] = [list(g) for g in self.matched_groups]
        return out


def _duplicate_sweep_result(
    slice_rows: list[dict[str, Any]],
    *,
    match_id_cap: int = _MATCH_ID_CAP,
) -> SweepResult:
    groups = duplicate_groups(slice_rows)
    matched_ids_set = set(duplicate_matched_ids(slice_rows))
    matched = [row for row in slice_rows if str(row.get("id") or "") in matched_ids_set]
    group_count = len(groups)
    match_count = len(matched)
    description = (
        f"Same requester email and normalized subject — {group_count} group(s), "
        f"{match_count} ticket(s). Likely webhook retries or double submits."
    )
    return SweepResult(
        id=DUPLICATE_SWEEP_ID,
        label="Possible duplicates",
        description=description,
        match_count=match_count,
        matched_ids=tuple(str(r.get("id") or "") for r in matched[:match_id_cap]),
        matched_groups=tuple(groups),
    )


def _rosetta_footer_sweep(slice_rows: list[dict[str, Any]], *, match_id_cap: int) -> SweepResult:
    ids = _match_ids_by_patterns(
        slice_rows,
        patterns=(r"thanks\.\s*rosetta\s+system\s+e-?mail", r"\brosetta\s+system\s+e-?mail\b"),
    )
    return _simple_sweep(
        sweep_id="rosetta_system_email",
        label="Rosetta System Email footer",
        description='Matches "Thanks. Rosetta System Email" — likely System Report, not Cancellation.',
        matched_ids=ids,
        match_id_cap=match_id_cap,
    )


def _esp_print_sweep(slice_rows: list[dict[str, Any]], *, match_id_cap: int) -> SweepResult:
    ids = _match_ids_by_patterns(
        slice_rows,
        patterns=(r"\bESP-OPP-\d+\b", r"\bESP-INV-\d+\b"),
    )
    return _simple_sweep(
        sweep_id="esp_print",
        label="ESP / Print signals",
        description="Matches ESP-OPP / ESP-INV — likely B2B/Print routed.",
        matched_ids=ids,
        match_id_cap=match_id_cap,
    )


def _posties_young_post_sweep(slice_rows: list[dict[str, Any]], *, match_id_cap: int) -> SweepResult:
    ids = _match_ids_by_patterns(
        slice_rows,
        patterns=(r"\bposties\b", r"\byoung\s+post\b"),
    )
    return _simple_sweep(
        sweep_id="posties_young_post",
        label="Posties / Young Post",
        description="Any mention — Christine routes these to B2B segment.",
        matched_ids=ids,
        match_id_cap=match_id_cap,
    )


def _delete_account_sweep(slice_rows: list[dict[str, Any]], *, match_id_cap: int) -> SweepResult:
    ids = _match_ids_by_patterns(
        slice_rows,
        patterns=(r"\bgdpr\b", r"\bdata\s+erasure\b", r"\berase\s+my\s+data\b", r"\bdelete\s+my\s+account\b"),
    )
    return _simple_sweep(
        sweep_id="delete_account_gdpr",
        label="Account deletion (GDPR / data erasure)",
        description="Signals a delete-account request — should route to the dedicated deletion category.",
        matched_ids=ids,
        match_id_cap=match_id_cap,
    )


def _invoice_sweep(slice_rows: list[dict[str, Any]], *, match_id_cap: int) -> SweepResult:
    ids = _match_ids_by_patterns(
        slice_rows,
        patterns=(r"\binvoice\b", r"\bpo\b", r"发票"),
    )
    return _simple_sweep(
        sweep_id="invoice_request",
        label="Invoice / PO request",
        description="Invoice / 发票 / PO request language — should route to Billing & Admin invoices.",
        matched_ids=ids,
        match_id_cap=match_id_cap,
    )


def _refund_cancel_combo_sweep(slice_rows: list[dict[str, Any]], *, match_id_cap: int) -> SweepResult:
    ids: list[str] = []
    for row in slice_rows:
        blob = _row_blob_lower(row)
        has_refund = bool(re.search(r"\brefund\b", blob))
        has_cancel = bool(re.search(r"\bcancel(?:lation)?\b", blob))
        if has_refund and has_cancel:
            tid = str(row.get("id") or "")
            if tid:
                ids.append(tid)
    return _simple_sweep(
        sweep_id="refund_cancel_combo",
        label="Refund + cancellation combo",
        description="Both refund and cancel language present — Christine prefers routing to Refund Request.",
        matched_ids=ids,
        match_id_cap=match_id_cap,
    )


def run_category_audit_sweeps(
    slice_rows: list[dict[str, Any]],
    allow: AllowList | None = None,
    *,
    match_id_cap: int = _MATCH_ID_CAP,
) -> list[SweepResult]:
    del allow
    return [
        _rosetta_footer_sweep(slice_rows, match_id_cap=match_id_cap),
        _esp_print_sweep(slice_rows, match_id_cap=match_id_cap),
        _posties_young_post_sweep(slice_rows, match_id_cap=match_id_cap),
        _delete_account_sweep(slice_rows, match_id_cap=match_id_cap),
        _invoice_sweep(slice_rows, match_id_cap=match_id_cap),
        _refund_cancel_combo_sweep(slice_rows, match_id_cap=match_id_cap),
        _duplicate_sweep_result(slice_rows, match_id_cap=match_id_cap),
    ]
