from pathlib import Path

import pytest
from openpyxl import Workbook

from cs_tickets.feedback.models import MineConfig
from cs_tickets.feedback.mine_rules import mine_rule_proposals
from cs_tickets.feedback.mine_taxonomy import mine_taxonomy_proposals
from cs_tickets.feedback.parse import LEARN_SHEET, parse_categorized_workbook
from cs_tickets.schema import TIER_FALLBACK_B2C_TBC
from cs_tickets.taxonomy import AllowList, load_allowlist


def _make_workbook(path: Path, rows: list[list[object]], header: list[str]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = LEARN_SHEET
    ws.append(header)
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_mine_any_tags_rule(tmp_path: Path) -> None:
    path = tmp_path / "tags.xlsx"
    header = ["id", "tags", "subject", "Tier1_Segment", "Tier2_Stream", "Tier3_Cat", "Tier4_Type"]
    tier = ["B2C", "Service Task", "Sales Leads", "Upgrade Inquiry"]
    rows = [
        [i, '["custom_learn_tag_xyz"]', f"Subject {i}", *tier]
        for i in range(1, 7)
    ]
    _make_workbook(path, rows, header)
    allow = AllowList(frozenset({(*tier, "N/A"), TIER_FALLBACK_B2C_TBC}))
    result = parse_categorized_workbook(path, upload_id="x", filename="tags.xlsx", allow=allow)
    assert result.rule_proposal_count >= 1
    assert any(
        "custom_learn_tag_xyz" in (p.all_tags or p.any_tags)
        for p in result.rule_proposals
    )
    assert all(p.support >= 5 for p in result.rule_proposals)


def test_mine_taxonomy_detects_new_tuple(tmp_path: Path) -> None:
    path = tmp_path / "new_tax.xlsx"
    header = ["id", "tags", "subject", "Tier1_Segment", "Tier2_Stream", "Tier3_Cat", "Tier4_Type"]
    new_tier = ["B2C", "Service Task", "General Support", "Brand New Type"]
    rows = [[1, '["tag_a"]', "Help me", *new_tier]]
    _make_workbook(path, rows, header)
    allow = AllowList(frozenset({("B2C", "Service Task", "General Support", "Other", "N/A")}))
    proposals = mine_taxonomy_proposals(
        [{"id": 1, "tags": '["tag_a"]', "subject": "Help me", **dict(zip(header[3:], new_tier, strict=True))}],
        allow,
    )
    assert len(proposals) == 1
    assert proposals[0].tier == (*new_tier, "N/A")
    assert proposals[0].novelty_type == "tier4_new"


def test_parse_with_mining_doc_reference(repo_root: Path) -> None:
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    tax = repo_root / "doc" / "Taxonomy.csv"
    if not xlsx.is_file() or not tax.is_file():
        pytest.skip("doc files missing")
    allow = load_allowlist(tax, xlsx)
    result = parse_categorized_workbook(
        xlsx,
        upload_id="test-upload",
        filename=xlsx.name,
        allow=allow,
    )
    assert result.row_count > 0
    assert result.eligible_row_count > 0
    assert result.rule_proposal_count >= 0
    assert result.taxonomy_proposal_count >= 0


def test_mine_skips_tbc_rows(tmp_path: Path) -> None:
    path = tmp_path / "tbc.xlsx"
    header = ["id", "tags", "subject", "Tier1_Segment", "Tier2_Stream", "Tier3_Cat", "Tier4_Type"]
    tbc = ["B2C", "Service Task", "General Support", "TBC (Manual Review)"]
    rows = [[i, '["shared_tag"]', f"Subject {i}", *tbc] for i in range(1, 8)]
    _make_workbook(path, rows, header)
    allow = AllowList(frozenset({(*tbc, "N/A")}))
    rules = mine_rule_proposals(
        [{"id": r[0], "tags": r[1], "subject": r[2], **dict(zip(header[3:], tbc, strict=True))} for r in rows],
        allow,
    )
    assert rules == ()


def test_dedupe_keeps_strongest_overlapping_proposals() -> None:
    tier = ("B2C", "Service Task", "General Support", "No Content - Live chat auto-trigger", "N/A")
    header = ["Tier1_Segment", "Tier2_Stream", "Tier3_Cat", "Tier4_Type"]
    row_dicts = [
        {
            "id": i,
            "tags": '["south_china_morning_post", "zopim_chat_ended"]',
            "subject": f"Conversation with visitor {i}",
            "description": "live chat transcript",
            **dict(zip(header, tier[:4], strict=True)),
            "Granular_Tech_UI_Type": "N/A",
        }
        for i in range(1, 7)
    ]
    allow = AllowList(frozenset({tier, TIER_FALLBACK_B2C_TBC}))
    proposals = mine_rule_proposals(
        row_dicts,
        allow,
        config=MineConfig(skip_already_classified=False),
    )
    live_chat = [p for p in proposals if p.tier == tier]
    assert len(live_chat) == 1
    assert live_chat[0].kind == "all_tags"


def test_mine_rules_handles_datetime_cells() -> None:
    from datetime import datetime

    tier = ("B2C", "Service Task", "Sales Leads", "Upgrade Inquiry", "N/A")
    rows = [
        {
            "id": i,
            "tags": '["custom_learn_tag_xyz"]',
            "subject": datetime(2026, 5, 14, 10, 30),
            "description": datetime(2026, 5, 14, 11, 0),
            "Tier1_Segment": tier[0],
            "Tier2_Stream": tier[1],
            "Tier3_Cat": tier[2],
            "Tier4_Type": tier[3],
            "Granular_Tech_UI_Type": "N/A",
        }
        for i in range(1, 7)
    ]
    allow = AllowList(frozenset({tier, TIER_FALLBACK_B2C_TBC}))
    proposals = mine_rule_proposals(rows, allow, config=MineConfig(skip_already_classified=True))
    assert proposals


def test_dedupe_collapses_live_chat_cluster_in_doc_workbook(repo_root: Path) -> None:
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    tax = repo_root / "doc" / "Taxonomy.csv"
    if not xlsx.is_file() or not tax.is_file():
        pytest.skip("doc files missing")
    from cs_tickets.feedback.parse import _read_workbook_rows, _row_is_eligible

    allow = load_allowlist(tax, xlsx)
    rows = [r for r in _read_workbook_rows(xlsx) if _row_is_eligible(r)]
    proposals = mine_rule_proposals(rows, allow)
    target = ("B2C", "Service Task", "General Support", "No Content - Live chat auto-trigger", "N/A")
    live_chat = [p for p in proposals if p.tier == target]
    overlap_triggers = {
        "conversation with",
        "south_china_morning_post",
        "zopim_chat_ended",
    }
    matching = [
        p
        for p in live_chat
        if (
            (p.any_blob and p.any_blob[0] == "conversation with")
            or (p.any_tags and p.any_tags[0] in overlap_triggers)
        )
    ]
    assert len(matching) <= 1
