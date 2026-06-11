from cs_tickets.portal_stats import (
    classify_run_counts,
    classify_run_summary_html,
    is_manual_review_row,
    tier_stats_display_rows,
    tier_stats_sheet_rows,
)


def test_is_manual_review_row() -> None:
    assert is_manual_review_row({"Tier4_Type": "TBC (Manual Review)"})
    assert not is_manual_review_row({"Tier4_Type": "Rate or Renewal Inquiry"})


def test_classify_run_counts_tbc_split() -> None:
    rows = [
        {
            "Tier1_Segment": "B2B",
            "Tier4_Type": "TBC (Manual Review)",
        },
        {
            "Tier1_Segment": "B2C",
            "Tier4_Type": "TBC (Manual Review)",
        },
        {
            "Tier1_Segment": "B2C",
            "Tier4_Type": "Rate or Renewal Inquiry",
        },
    ]
    counts = classify_run_counts(rows)
    assert counts.total == 3
    assert counts.tbc == 2
    assert counts.tbc_b2b == 1
    assert counts.tbc_b2c == 1


def test_classify_run_summary_html() -> None:
    rows = [{"Tier1_Segment": "B2C", "Tier4_Type": "TBC (Manual Review)"}] * 2
    rows.append({"Tier1_Segment": "B2C", "Tier4_Type": "Junk"})
    html = classify_run_summary_html(rows, warns=1)
    assert "3 tickets categorized" in html
    assert "manual review" in html
    assert "(TBC)" in html
    assert "66.7%" in html
    assert "technical warning" in html


def test_tier_stats_blanks_and_grand_total() -> None:
    rows = [
        {"Tier1_Segment": "B2C", "Tier2_Stream": "A", "Tier3_Cat": "X", "Tier4_Type": "L1"},
        {"Tier1_Segment": "B2C", "Tier2_Stream": "A", "Tier3_Cat": "X", "Tier4_Type": "L1"},
        {"Tier1_Segment": "B2C", "Tier2_Stream": "A", "Tier3_Cat": "Y", "Tier4_Type": "L2"},
    ]
    body, grand = tier_stats_display_rows(rows)
    assert grand == 3
    assert len(body) == 2
    assert body[0] == ["B2C", "A", "X", "L1", "2"]
    assert body[1][0] == "" and body[1][1] == "" and body[1][2] == "Y"
    assert body[1][3] == "L2" and body[1][4] == "1"


def test_tier_stats_sheet_rows_grand_total() -> None:
    rows = [
        {"Tier1_Segment": "B2C", "Tier2_Stream": "A", "Tier3_Cat": "X", "Tier4_Type": "L1"},
        {"Tier1_Segment": "B2C", "Tier2_Stream": "A", "Tier3_Cat": "X", "Tier4_Type": "L1"},
    ]
    header, data = tier_stats_sheet_rows(rows)
    assert header[4] == "COUNTA of id"
    assert data[-1] == ["Grand Total", "", "", "", 2]
    assert data[0][4] == 2
