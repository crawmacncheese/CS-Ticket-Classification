"""Build classified .xlsx upload for allowlist Training TBC probe test."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from openpyxl import Workbook

from cs_tickets.flatten import flatten_ticket
from cs_tickets.schema import MASTER_COLUMNS, TIER_COLUMNS

SHEET = "SCMP_Tickets_Master_Categorized"
PROBE_TUPLE = (
    "B2C",
    "Service Task",
    "Sales Leads",
    "Rate or Renewal Inquiry",
    "N/A",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ndjson",
        type=Path,
        default=Path("tests/fixtures/training_tbc_probe.ndjson"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/fixtures/training_tbc_probe_upload.xlsx"),
    )
    args = parser.parse_args()

    line = next(ln for ln in args.ndjson.read_text(encoding="utf-8").splitlines() if ln.strip())
    flat = flatten_ticket(json.loads(line))

    row = {c: "" for c in MASTER_COLUMNS}
    row.update(flat)
    row["id"] = str(flat.get("id") or "")
    for col, val in zip(TIER_COLUMNS, PROBE_TUPLE):
        row[col] = val

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(list(MASTER_COLUMNS))
    ws.append([row.get(c, "") for c in MASTER_COLUMNS])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(args.out)
    print(f"Wrote {args.out}")
    print(f"Tuple: {' | '.join(PROBE_TUPLE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
