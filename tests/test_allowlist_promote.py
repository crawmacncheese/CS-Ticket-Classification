from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from openpyxl import Workbook

from cs_tickets.feedback.models import TaxonomyProposal
from cs_tickets.feedback.promote import (
    PromoteError,
    backup_live_dir,
    confirm_hybrid_proposals,
    merge_taxonomy_csv,
    restore_live_dir,
)
from cs_tickets.live_config import RULES_FILE, TAXONOMY_FILE, WORKBOOK_FILE
from cs_tickets.runtime_config import ensure_live_bootstrapped
from cs_tickets.schema import MASTER_COLUMNS
from cs_tickets.taxonomy import load_allowlist, novelty_type_for_tuple, split_taxonomy_proposals

_SHEET = "SCMP_Tickets_Master_Categorized"

_BASE_TUPLE = (
    "B2C",
    "Service Task",
    "Billing & Admin",
    "Invoice Inquiry",
    "N/A",
)

_GRANULAR_TUPLE = (
    "B2C",
    "Service Task",
    "Billing & Admin",
    "Invoice Inquiry",
    "Portal Login",
)


def _seed_doc_tree(repo_root: Path, target: Path) -> None:
    shutil.copytree(repo_root / "doc", target / "doc")


def _write_taxonomy_csv(path: Path, body: str) -> None:
    path.write_text(
        "Tier1_Segment,Tier2_Stream,Tier3_Cat,Tier4_Type\n" + body,
        encoding="utf-8",
    )


def _write_classified_xlsx(path: Path, rows: list[dict[str, str]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = _SHEET
    ws.append(list(MASTER_COLUMNS))
    for row in rows:
        ws.append([row.get(col, "") for col in MASTER_COLUMNS])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def _exemplar_row(tier: tuple[str, str, str, str, str], *, ticket_id: str = "9001") -> dict[str, str]:
    return {
        "url": "https://example.zendesk.com/tickets/9001",
        "id": ticket_id,
        "subject": "Invoice portal login issue",
        "description": "Customer cannot access invoice portal",
        "tags": '["billing", "portal_login"]',
        "Tier1_Segment": tier[0],
        "Tier2_Stream": tier[1],
        "Tier3_Cat": tier[2],
        "Tier4_Type": tier[3],
        "Granular_Tech_UI_Type": tier[4],
    }


def _bootstrap_live(tmp_path: Path, repo_root: Path, *, taxonomy_body: str) -> Path:
    _seed_doc_tree(repo_root, tmp_path)
    live = ensure_live_bootstrapped(tmp_path)
    _write_taxonomy_csv(live / TAXONOMY_FILE, taxonomy_body)
    return live


def _proposal(
    tier: tuple[str, str, str, str, str],
    *,
    novelty: str,
    proposal_id: str | None = None,
) -> TaxonomyProposal:
    slug = "-".join(tier).lower().replace(" ", "-")
    return TaxonomyProposal(
        proposal_id=proposal_id or f"tax.{slug[:40]}",
        tier=tier,
        count=1,
        novelty_type=novelty,
        evidence_ids=("9001",),
    )


def test_split_taxonomy_granular_routes_to_workbook_only() -> None:
    proposal = _proposal(_GRANULAR_TUPLE, novelty="granular_new")
    csv_proposals, workbook_tuples = split_taxonomy_proposals((proposal,))
    assert csv_proposals == ()
    assert workbook_tuples == frozenset({_GRANULAR_TUPLE})


def test_split_taxonomy_tier4_routes_to_csv_only() -> None:
    tier = ("B2C", "Service Task", "Billing & Admin", "New Tier4 Type", "N/A")
    proposal = _proposal(tier, novelty="tier4_new")
    csv_proposals, workbook_tuples = split_taxonomy_proposals((proposal,))
    assert len(csv_proposals) == 1
    assert workbook_tuples == frozenset()


def test_split_taxonomy_tier4_with_granular_routes_to_both() -> None:
    tier = ("B2C", "Service Task", "Billing & Admin", "New Tier4 Type", "Portal Login")
    proposal = _proposal(tier, novelty="tier4_new")
    csv_proposals, workbook_tuples = split_taxonomy_proposals((proposal,))
    assert len(csv_proposals) == 1
    assert workbook_tuples == frozenset({tier})


def test_novelty_type_granular_when_path_exists(tmp_path: Path, repo_root: Path) -> None:
    live = _bootstrap_live(
        tmp_path,
        repo_root,
        taxonomy_body="B2C,Service Task,Billing & Admin,Invoice Inquiry\n",
    )
    allow = load_allowlist(live / TAXONOMY_FILE, live / WORKBOOK_FILE)
    assert novelty_type_for_tuple(_GRANULAR_TUPLE, allow) == "granular_new"


def test_confirm_granular_new_adds_workbook_tuple(tmp_path: Path, repo_root: Path) -> None:
    live = _bootstrap_live(
        tmp_path,
        repo_root,
        taxonomy_body="B2C,Service Task,Billing & Admin,Invoice Inquiry\n",
    )
    allow_before = load_allowlist(live / TAXONOMY_FILE, live / WORKBOOK_FILE)
    assert _BASE_TUPLE in allow_before.tuples
    assert _GRANULAR_TUPLE not in allow_before.tuples

    upload = tmp_path / "upload.xlsx"
    _write_classified_xlsx(upload, [_exemplar_row(_GRANULAR_TUPLE)])
    proposal = _proposal(_GRANULAR_TUPLE, novelty="granular_new", proposal_id="tax.granular")

    result = confirm_hybrid_proposals(
        live,
        upload_id="upload-granular",
        upload_filename="upload.xlsx",
        upload_xlsx=upload,
        rule_proposals=(),
        taxonomy_proposals=(proposal,),
        accepted_rule_ids=frozenset(),
        accepted_taxonomy_ids=frozenset({"tax.granular"}),
    )

    assert result.workbook_rows_added == 1
    assert result.taxonomy_added == 0
    allow_after = load_allowlist(live / TAXONOMY_FILE, live / WORKBOOK_FILE)
    assert _GRANULAR_TUPLE in allow_after.tuples
    csv_text = (live / TAXONOMY_FILE).read_text(encoding="utf-8")
    assert csv_text.count("Portal Login") == 0


def test_confirm_tier4_new_adds_csv_path(tmp_path: Path, repo_root: Path) -> None:
    live = _bootstrap_live(
        tmp_path,
        repo_root,
        taxonomy_body="B2C,Service Task,Billing & Admin,Invoice Inquiry\n",
    )
    new_tuple = ("B2C", "Service Task", "General Support", "Account Access", "N/A")
    upload = tmp_path / "upload.xlsx"
    _write_classified_xlsx(upload, [_exemplar_row(new_tuple, ticket_id="9002")])
    proposal = _proposal(new_tuple, novelty="tier4_new", proposal_id="tax.tier4")

    result = confirm_hybrid_proposals(
        live,
        upload_id="upload-tier4",
        upload_filename="upload.xlsx",
        upload_xlsx=upload,
        rule_proposals=(),
        taxonomy_proposals=(proposal,),
        accepted_rule_ids=frozenset(),
        accepted_taxonomy_ids=frozenset({"tax.tier4"}),
    )

    assert result.taxonomy_added == 1
    assert result.workbook_rows_added == 0
    allow_after = load_allowlist(live / TAXONOMY_FILE, live / WORKBOOK_FILE)
    assert new_tuple in allow_after.tuples


def test_confirm_both_csv_and_workbook_in_one_confirm(tmp_path: Path, repo_root: Path) -> None:
    live = _bootstrap_live(
        tmp_path,
        repo_root,
        taxonomy_body="B2C,Service Task,Billing & Admin,Invoice Inquiry\n",
    )
    tier4_tuple = ("B2C", "Service Task", "General Support", "Password Reset", "N/A")
    upload = tmp_path / "upload.xlsx"
    _write_classified_xlsx(
        upload,
        [
            _exemplar_row(_GRANULAR_TUPLE, ticket_id="9003"),
            _exemplar_row(tier4_tuple, ticket_id="9004"),
        ],
    )
    granular_proposal = _proposal(_GRANULAR_TUPLE, novelty="granular_new", proposal_id="tax.granular")
    tier4_proposal = _proposal(tier4_tuple, novelty="tier4_new", proposal_id="tax.tier4")

    result = confirm_hybrid_proposals(
        live,
        upload_id="upload-both",
        upload_filename="upload.xlsx",
        upload_xlsx=upload,
        rule_proposals=(),
        taxonomy_proposals=(granular_proposal, tier4_proposal),
        accepted_rule_ids=frozenset(),
        accepted_taxonomy_ids=frozenset({"tax.granular", "tax.tier4"}),
    )

    assert result.taxonomy_added == 1
    assert result.workbook_rows_added == 1
    allow_after = load_allowlist(live / TAXONOMY_FILE, live / WORKBOOK_FILE)
    assert _GRANULAR_TUPLE in allow_after.tuples
    assert tier4_tuple in allow_after.tuples


def test_confirm_validation_failure_restores_backup(tmp_path: Path, repo_root: Path) -> None:
    live = _bootstrap_live(
        tmp_path,
        repo_root,
        taxonomy_body="B2C,Service Task,Billing & Admin,Invoice Inquiry\n",
    )
    version_before = json.loads((live / "config_version.json").read_text(encoding="utf-8"))["version"]
    tax_before = (live / TAXONOMY_FILE).read_text(encoding="utf-8")
    rules_before = (live / RULES_FILE).read_text(encoding="utf-8")

    proposal = _proposal(_GRANULAR_TUPLE, novelty="granular_new", proposal_id="tax.fail")
    with pytest.raises(PromoteError, match="Upload workbook required"):
        confirm_hybrid_proposals(
            live,
            upload_id="upload-fail",
            upload_filename="upload.xlsx",
            upload_xlsx=None,
            rule_proposals=(),
            taxonomy_proposals=(proposal,),
            accepted_rule_ids=frozenset(),
            accepted_taxonomy_ids=frozenset({"tax.fail"}),
        )

    version_after = json.loads((live / "config_version.json").read_text(encoding="utf-8"))["version"]
    assert version_after == version_before
    assert (live / TAXONOMY_FILE).read_text(encoding="utf-8") == tax_before
    assert (live / RULES_FILE).read_text(encoding="utf-8") == rules_before


def test_merge_taxonomy_csv_idempotent_for_existing_path() -> None:
    csv_text = "Tier1_Segment,Tier2_Stream,Tier3_Cat,Tier4_Type\nB2C,Service Task,Billing & Admin,Invoice Inquiry\n"
    proposal = _proposal(_BASE_TUPLE, novelty="tier4_new")
    merged, added = merge_taxonomy_csv(csv_text, (proposal,))
    assert added == 0
    assert merged.strip() == csv_text.strip()


def test_backup_restore_round_trip(tmp_path: Path, repo_root: Path) -> None:
    live = _bootstrap_live(
        tmp_path,
        repo_root,
        taxonomy_body="B2C,Service Task,Billing & Admin,Invoice Inquiry\n",
    )
    backup_dir = live / "backup" / "test"
    backup_live_dir(live, backup_dir)
    (live / TAXONOMY_FILE).write_text("Tier1_Segment,Tier2_Stream,Tier3_Cat,Tier4_Type\n", encoding="utf-8")
    restore_live_dir(live, backup_dir)
    assert "Invoice Inquiry" in (live / TAXONOMY_FILE).read_text(encoding="utf-8")


def test_build_candidate_live_config_matches_confirm_granular(
    tmp_path: Path, repo_root: Path
) -> None:
    live = _bootstrap_live(
        tmp_path,
        repo_root,
        taxonomy_body="B2C,Service Task,Billing & Admin,Invoice Inquiry\n",
    )
    upload = tmp_path / "upload.xlsx"
    _write_classified_xlsx(upload, [_exemplar_row(_GRANULAR_TUPLE)])
    proposal = _proposal(_GRANULAR_TUPLE, novelty="granular_new", proposal_id="tax.granular")

    from cs_tickets.feedback.promote import (
        build_candidate_live_config,
        release_candidate_live_config,
    )

    candidate = build_candidate_live_config(
        live,
        upload_xlsx=upload,
        rule_proposals=(),
        taxonomy_proposals=(proposal,),
        accepted_rule_ids=frozenset(),
        accepted_taxonomy_ids=frozenset({"tax.granular"}),
    )
    try:
        assert _GRANULAR_TUPLE in candidate.allow_new.tuples
        assert _GRANULAR_TUPLE not in candidate.allow_old.tuples
    finally:
        release_candidate_live_config(candidate)

    confirm_hybrid_proposals(
        live,
        upload_id="upload-candidate-parity",
        upload_filename="upload.xlsx",
        upload_xlsx=upload,
        rule_proposals=(),
        taxonomy_proposals=(proposal,),
        accepted_rule_ids=frozenset(),
        accepted_taxonomy_ids=frozenset({"tax.granular"}),
    )
    allow_after = load_allowlist(live / TAXONOMY_FILE, live / WORKBOOK_FILE)
    assert candidate.allow_new.tuples == allow_after.tuples
