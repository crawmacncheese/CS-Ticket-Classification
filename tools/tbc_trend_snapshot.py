from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from cs_tickets.taxonomy import load_allowlist
from cs_tickets.tbc_trends import append_export_snapshot, classifier_version_hash, init_db


def _collect_ndjson_paths(args: argparse.Namespace) -> list[Path]:
    if args.ndjson is not None and args.ndjson_dir is not None:
        print("error: supply exactly one of --ndjson or --ndjson-dir", file=sys.stderr)
        raise SystemExit(2)
    if args.ndjson is not None:
        if not args.ndjson.is_file():
            print(f"error: NDJSON not found: {args.ndjson}", file=sys.stderr)
            raise SystemExit(1)
        return [args.ndjson]
    if args.ndjson_dir is not None:
        paths = sorted(
            {p for pattern in ("*.ndjson", "*.json") for p in args.ndjson_dir.glob(pattern)}
        )
        if not paths:
            print(
                f"error: no *.ndjson or *.json exports in {args.ndjson_dir}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        return paths
    print("error: --ndjson or --ndjson-dir is required", file=sys.stderr)
    raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify NDJSON exports and append TBC trend snapshots to SQLite",
    )
    parser.add_argument("--ndjson", type=Path, default=None)
    parser.add_argument("--ndjson-dir", type=Path, default=None)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("reports/tbc_trends/tbc_trends.db"),
        help="SQLite database path (created if missing)",
    )
    parser.add_argument("--taxonomy", type=Path, default=Path("doc/Taxonomy.csv"))
    parser.add_argument("--workbook", type=Path, default=Path("doc/CS_ticket_new_categorizations.xlsx"))
    parser.add_argument(
        "--bad-satisfaction-only",
        action="store_true",
        help="Only include tickets with bad satisfaction rating",
    )
    args = parser.parse_args()

    paths = _collect_ndjson_paths(args)
    allow = load_allowlist(args.taxonomy, args.workbook)
    conn = init_db(args.db)
    version = classifier_version_hash()
    print(f"classifier_version: {version}")
    print(f"database: {args.db.resolve()}")

    grand_rows = 0
    grand_tbc = 0
    for path in paths:
        rows, tbc = append_export_snapshot(
            conn,
            path,
            allow,
            bad_satisfaction_only=args.bad_satisfaction_only,
        )
        pct = 100.0 * tbc / rows if rows else 0.0
        print(f"{path.name}: {rows} rows, {tbc} TBC ({pct:.1f}%)")
        grand_rows += rows
        grand_tbc += tbc

    if len(paths) > 1:
        pct = 100.0 * grand_tbc / grand_rows if grand_rows else 0.0
        print(f"total: {grand_rows} rows, {grand_tbc} TBC ({pct:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
