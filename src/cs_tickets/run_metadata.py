"""Run-level metadata for workbook export and Google Drive uploads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunMetadata:
    run_id: str
    source_filename: str
    row_count: int
    warning_count: int
    tbc_count: int
    created_at_utc: str
    bad_satisfaction_only: bool = False

    def metadata_sheet_rows(self) -> list[tuple[str, str]]:
        rows = [
            ("run_id", self.run_id),
            ("source_filename", self.source_filename),
            ("row_count", str(self.row_count)),
            ("tbc_count", str(self.tbc_count)),
            ("tbc_pct", f"{100.0 * self.tbc_count / self.row_count:.1f}%" if self.row_count else "0%"),
            ("classifier_warnings", str(self.warning_count)),
            ("created_at_utc", self.created_at_utc),
        ]
        if self.bad_satisfaction_only:
            rows.append(("filter", "bad_satisfaction_only"))
        return rows


def count_tbc_rows(rows: list[dict[str, Any]]) -> int:
    return sum(1 for r in rows if "tbc" in (r.get("Tier4_Type") or "").lower())


def build_run_metadata(
    *,
    run_id: str,
    source_filename: str,
    rows: list[dict[str, Any]],
    warning_count: int,
    created_at: datetime | None = None,
    bad_satisfaction_only: bool = False,
) -> RunMetadata:
    when = created_at or datetime.now(timezone.utc)
    return RunMetadata(
        run_id=run_id,
        source_filename=source_filename,
        row_count=len(rows),
        warning_count=warning_count,
        tbc_count=count_tbc_rows(rows),
        created_at_utc=when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        bad_satisfaction_only=bad_satisfaction_only,
    )


def build_workbook_filename(
    *,
    source_filename: str,
    run_id: str,
    created_at: datetime | None = None,
) -> str:
    when = created_at or datetime.now(timezone.utc)
    stem = Path(source_filename).stem or "export"
    safe = re.sub(r"[^\w.-]+", "_", stem).strip("_")[:60] or "export"
    return f"master_{when.strftime('%Y%m%d')}_{safe}_{run_id[:8]}.xlsx"
