from __future__ import annotations

from pathlib import Path

import pytest

from cs_tickets.taxonomy import load_allowlist
from cs_tickets.tbc_trends import (
    append_export_snapshot,
    init_db,
    iter_trend_records,
    load_subject_cluster_rollup,
    load_weekly_rollup,
    subject_cluster_key,
    week_bucket,
    write_trend_reports,
)


def test_subject_cluster_key_normalizes_reply_and_digits() -> None:
    assert subject_cluster_key("RE: Order 12345 confirmation") == "order # confirmation"
    assert subject_cluster_key("FW:  Hello   world") == "hello world"
    assert subject_cluster_key("") == "(empty)"


def test_week_bucket_iso_week() -> None:
    assert week_bucket("2025-01-15T12:00:00Z") == "2025-W03"
    assert week_bucket("") == "unknown"


def _require_doc(repo_root: Path) -> tuple[Path, Path]:
    tax = repo_root / "doc" / "Taxonomy.csv"
    ref = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not ref.is_file():
        pytest.skip("doc artifacts missing")
    return tax, ref


def test_snapshot_and_report_round_trip(repo_root: Path, tmp_path: Path) -> None:
    tax, ref = _require_doc(repo_root)
    ndjson = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    if not ndjson.is_file():
        pytest.skip("fixture missing")

    allow = load_allowlist(tax, ref)
    db_path = tmp_path / "tbc.db"
    conn = init_db(db_path)
    rows, tbc = append_export_snapshot(conn, ndjson, allow)
    assert rows == 5
    assert tbc >= 0

    weekly = load_weekly_rollup(conn)
    assert sum(r.total for r in weekly) == 5

    out_dir = tmp_path / "reports"
    written = write_trend_reports(out_dir, conn)
    assert (out_dir / "summary.md").is_file()
    assert len(written) == 5
    summary = (out_dir / "summary.md").read_text(encoding="utf-8")
    assert "TBC Trend Summary" in summary
    assert "five_tickets" in summary or "900001" in summary or str(rows) in summary

    conn.close()


def test_iter_trend_records_matches_row_count(repo_root: Path) -> None:
    tax, ref = _require_doc(repo_root)
    ndjson = repo_root / "tests" / "fixtures" / "five_tickets.ndjson"
    allow = load_allowlist(tax, ref)
    records = list(iter_trend_records(ndjson, allow))
    assert len(records) == 5
    assert all(r.ticket_id for r in records)
    assert all(r.week_bucket == "2025-W01" for r in records)


def test_cluster_rollup_groups_normalized_subjects(tmp_path: Path) -> None:
    tax_path = tmp_path / "Taxonomy.csv"
    tax_path.write_text("Tier1,Tier2,Tier3,Tier4\n", encoding="utf-8")
    # Minimal allow-list not needed if we only test DB rollup shape — use real doc if present
    repo_root = Path(__file__).resolve().parents[1]
    tax, ref = _require_doc(repo_root)
    allow = load_allowlist(tax, ref)

    ndjson = tmp_path / "reply.ndjson"
    ndjson.write_text(
        "\n".join(
            [
                '{"id":1,"created_at":"2025-06-01T00:00:00Z","updated_at":"2025-06-01T00:00:00Z","subject":"RE: Billing issue 9999","tags":["miscellaneous"],"description":""}',
                '{"id":2,"created_at":"2025-06-02T00:00:00Z","updated_at":"2025-06-02T00:00:00Z","subject":"Re: Billing issue 8888","tags":["miscellaneous"],"description":""}',
            ]
        ),
        encoding="utf-8",
    )
    conn = init_db(tmp_path / "t.db")
    append_export_snapshot(conn, ndjson, allow)
    clusters = load_subject_cluster_rollup(conn)
    billing = [c for c in clusters if "billing" in c["subject_cluster"]]
    assert billing
    assert billing[0]["tbc_count"] >= 1
