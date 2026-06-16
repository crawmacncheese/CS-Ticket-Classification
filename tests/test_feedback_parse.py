from pathlib import Path

import pytest

from cs_tickets.feedback.parse import LEARN_SHEET, parse_categorized_workbook
from cs_tickets.taxonomy import load_allowlist


def test_parse_categorized_workbook_doc_reference(repo_root: Path) -> None:
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    tax = repo_root / "doc" / "Taxonomy.csv"
    if not xlsx.is_file():
        pytest.skip("doc workbook missing")
    allow = load_allowlist(tax if tax.is_file() else None, xlsx if xlsx.is_file() else None)
    result = parse_categorized_workbook(
        xlsx,
        upload_id="test-upload",
        filename=xlsx.name,
        allow=allow,
    )
    assert result.row_count > 0
    assert result.eligible_row_count > 0
    assert result.distinct_tier_paths > 0
    assert result.rule_proposal_count >= 0
    assert result.taxonomy_proposal_count >= 0
    assert result.status == "processed"


def test_parse_workbook_without_granular_column(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "four_tiers.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = LEARN_SHEET
    ws.append(
        [
            "url",
            "id",
            "tags",
            "subject",
            "description",
            "Tier1_Segment",
            "Tier2_Stream",
            "Tier3_Cat",
            "Tier4_Type",
        ]
    )
    ws.append(
        [
            "https://example.test/1",
            1,
            '["tag_a"]',
            "Test subject",
            "Test description",
            "B2C",
            "Service Task",
            "General Support",
            "TBC (Manual Review)",
        ]
    )
    wb.save(path)
    result = parse_categorized_workbook(path, upload_id="x", filename="four_tiers.xlsx")
    assert result.eligible_row_count == 1
    assert result.distinct_tier_paths == 1


def test_normalize_ticket_id_strips_excel_float_suffix() -> None:
    from cs_tickets.feedback.ids import normalize_ticket_id

    assert normalize_ticket_id(168595.0) == "168595"
    assert normalize_ticket_id("168595.0") == "168595"
    assert normalize_ticket_id(168595) == "168595"
    assert normalize_ticket_id("168595") == "168595"
    assert normalize_ticket_id(None) == ""


def test_parse_rejects_missing_sheet(tmp_path: Path) -> None:
    from openpyxl import Workbook

    path = tmp_path / "empty.xlsx"
    Workbook().save(path)
    with pytest.raises(ValueError, match="No sheet with ticket rows"):
        parse_categorized_workbook(path, upload_id="x", filename="empty.xlsx")
