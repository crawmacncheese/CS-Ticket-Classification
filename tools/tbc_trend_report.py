from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from cs_tickets.tbc_trends import init_db, write_trend_reports


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate TBC trend rollups (markdown + CSV) from snapshot database",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("reports/tbc_trends/tbc_trends.db"),
        help="SQLite database from tbc_trend_snapshot.py",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports/tbc-trends"),
        help="Directory for summary.md and rollup CSVs",
    )
    args = parser.parse_args()

    if not args.db.is_file():
        print(f"error: database not found: {args.db}", file=sys.stderr)
        print("Run tools/tbc_trend_snapshot.py first.", file=sys.stderr)
        return 1

    conn = init_db(args.db)
    written = write_trend_reports(args.output_dir, conn)
    conn.close()

    print(f"reports written to {args.output_dir.resolve()}")
    for path in written:
        print(f"  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
