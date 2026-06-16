from __future__ import annotations

from pathlib import Path

import typer

from cs_tickets.classifier_rules import set_active_rule_specs
from cs_tickets.pipeline import run_to_csv
from cs_tickets.repo_paths import resolve_repo_root
from cs_tickets.runtime_config import (
    ensure_live_bootstrapped,
    load_runtime_allowlist,
    load_runtime_rule_specs,
)
from cs_tickets.taxonomy import load_allowlist

app = typer.Typer(help="SCMP CS ticket export → master CSV (flatten + tiers).")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    input_path: Path | None = typer.Option(
        None,
        "--input",
        "-i",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Zendesk NDJSON export (one ticket JSON per line).",
    ),
    out_path: Path = typer.Option(
        Path("out/master_categorized.csv"),
        "--out",
        "-o",
        help="Output CSV path.",
    ),
    taxonomy: Path | None = typer.Option(
        None,
        "--taxonomy",
        help="Pivot-style taxonomy CSV (default: doc/Taxonomy.csv under repo root).",
    ),
    workbook: Path | None = typer.Option(
        None,
        "--workbook",
        help="Reference xlsx for tier allow-list union (default: doc/CS_ticket_new_categorizations.xlsx).",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Process at most N tickets (for quick tests).",
    ),
    bad_satisfaction_only: bool = typer.Option(
        False,
        "--bad-satisfaction-only",
        help="Only categorize tickets with Zendesk CSAT score bad.",
    ),
) -> None:
    """Build categorized master rows from a Zendesk NDJSON export."""
    if ctx.invoked_subcommand is not None:
        return
    if input_path is None:
        typer.echo(ctx.get_help(), err=True)
        raise typer.Exit(code=2)
    root = resolve_repo_root()
    if taxonomy is None and workbook is None:
        ensure_live_bootstrapped(root)
        set_active_rule_specs(load_runtime_rule_specs(root))
        allow = load_runtime_allowlist(root)
    else:
        tax = taxonomy or (root / "doc" / "Taxonomy.csv")
        wb = workbook or (root / "doc" / "CS_ticket_new_categorizations.xlsx")
        allow = load_allowlist(tax if tax.is_file() else None, wb if wb.is_file() else None)
    n, warns = run_to_csv(
        input_path,
        allow,
        out_path,
        limit=limit,
        bad_satisfaction_only=bad_satisfaction_only,
    )
    filter_note = " (bad CSAT only)" if bad_satisfaction_only else ""
    typer.echo(f"Wrote {n} rows to {out_path}{filter_note} ({warns} rows with classifier warnings).")


if __name__ == "__main__":
    app()
