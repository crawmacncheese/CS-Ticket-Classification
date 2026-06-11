from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from cs_tickets.allowlist_training import build_candidate_rule_set_from_upload
from cs_tickets.batch_allowlist_analysis import (
    apply_ablation_no_op_to_result,
    build_candidate_allowlist_cli,
    parse_inline_tuple,
    resolve_selected_tuples,
    run_commit_simulation,
    run_tuple_ablation,
    write_ablation_reports,
    write_batch_reports,
    write_summary_markdown,
)
from cs_tickets.taxonomy import AllowList, load_allowlist


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
    parser = argparse.ArgumentParser(description="Batch allow-list impact analysis")
    parser.add_argument("--ndjson", type=Path, default=None)
    parser.add_argument("--ndjson-dir", type=Path, default=None)
    parser.add_argument("--taxonomy", type=Path, default=Path("doc/Taxonomy.csv"))
    parser.add_argument("--workbook", type=Path, default=Path("doc/CS_ticket_new_categorizations.xlsx"))
    parser.add_argument("--merge-tuples", action="append", default=[], metavar="T1,T2,T3,T4,T5")
    parser.add_argument("--merge-tuples-from", type=Path, default=None)
    parser.add_argument("--selected-tuples-json", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--with-rules", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--compute-no-op", action="store_true")
    parser.add_argument("--ablation", action="store_true")
    parser.add_argument("--ablation-limit", type=int, default=None)
    parser.add_argument(
        "--enrich-rows",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    allow_old = load_allowlist(args.taxonomy, args.workbook)
    inline = [parse_inline_tuple(t) for t in args.merge_tuples]

    try:
        selected = resolve_selected_tuples(
            allow_old=allow_old,
            inline_tuples=inline or None,
            merge_tuples_from=args.merge_tuples_from,
            selected_tuples_json=args.selected_tuples_json,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.with_rules and args.merge_tuples_from is None:
        print("error: --with-rules requires --merge-tuples-from for exemplar rows", file=sys.stderr)
        raise SystemExit(1)

    ndjson_paths = _collect_ndjson_paths(args)

    upload_path = args.merge_tuples_from
    with tempfile.TemporaryDirectory(prefix="cs_batch_") as tmp:
        work_dir = Path(tmp)
        if upload_path is not None:
            allow_new, _ = build_candidate_allowlist_cli(
                repo_root,
                upload_path,
                selected,
                work_dir,
            )
            rule_specs_new = (
                build_candidate_rule_set_from_upload(repo_root, upload_path, selected)
                if args.with_rules
                else None
            )
        else:
            allow_new = AllowList(tuples=frozenset(allow_old.tuples | selected))
            rule_specs_new = None

        result = run_commit_simulation(
            ndjson_paths,
            allow_old,
            allow_new,
            selected_tuples=selected,
            rule_specs_new=rule_specs_new,
            limit=args.limit,
            enrich_changed_rows=args.enrich_rows,
            compute_no_op=args.compute_no_op and not args.ablation,
        )

        ablation = None
        if args.ablation:
            rule_builder = None
            if args.with_rules and upload_path is not None:
                rule_builder = lambda t: build_candidate_rule_set_from_upload(  # noqa: E731
                    repo_root, upload_path, frozenset({t})
                )
            ablation = run_tuple_ablation(
                ndjson_paths,
                allow_old,
                selected,
                rule_specs_builder=rule_builder,
                limit=args.limit,
                ablation_limit=args.ablation_limit,
                enrich_changed_rows=args.enrich_rows,
            )
            result = apply_ablation_no_op_to_result(result, ablation)
            write_ablation_reports(ablation, args.output_dir)

        write_batch_reports(result, args.output_dir)
        write_summary_markdown(
            result,
            args.output_dir,
            ablation=ablation,
            ndjson_paths=ndjson_paths,
        )

    print(f"Wrote reports to {args.output_dir}")
    print(f"verdict_band: {result.verdict_band}")
    print(f"net_tbc_improvement: {result.combined.tbc_old - result.combined.tbc_new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
