from pathlib import Path

import json
import pytest

from cs_tickets.feedback.models import RuleProposal, TaxonomyProposal
from cs_tickets.feedback.promote import (
    PromoteError,
    confirm_learn_proposals,
    merge_rules_json,
    merge_taxonomy_csv,
    read_config_version,
    rule_proposal_to_json,
)
from cs_tickets.runtime_config import ensure_live_bootstrapped


def test_rule_proposal_to_json() -> None:
    proposal = RuleProposal(
        proposal_id="rule.learn.test_tag",
        kind="any_tags",
        tier=("B2C", "Service Task", "General Support", "Login Issue", "N/A"),
        weight=11.0,
        support=8,
        purity=1.0,
        any_tags=("login_issue",),
    )
    raw = rule_proposal_to_json(proposal)
    assert raw["id"] == "learn.test_tag"
    assert raw["any_tags"] == ["login_issue"]


def test_merge_taxonomy_csv_appends_path() -> None:
    base = "Tier1_Segment,Tier2_Stream,Tier3_Cat,Tier4_Type\nB2C,Service Task,General Support,Existing\n"
    proposal = TaxonomyProposal(
        proposal_id="tax.new",
        tier=("B2C", "Service Task", "General Support", "Brand New Type", "N/A"),
        count=3,
        novelty_type="tier4_new",
    )
    merged, added = merge_taxonomy_csv(base, (proposal,))
    assert added == 1
    assert "Brand New Type" in merged
    assert merged.count("Existing") == 1


def test_merge_taxonomy_csv_inserts_before_grand_total_in_service_task_section() -> None:
    base = Path("doc/Taxonomy.csv").read_text(encoding="utf-8")
    proposal = TaxonomyProposal(
        proposal_id="tax.cancel",
        tier=("B2C", "Service Task", "Need help for Cancellation", "Cancellation Request", "N/A"),
        count=11,
        novelty_type="tier4_new",
    )
    merged, added = merge_taxonomy_csv(base, (proposal,))
    assert added == 1
    lines = merged.splitlines()
    grand_idx = next(i for i, line in enumerate(lines) if line.lower().startswith("grand total"))
    cancel_idx = next(i for i, line in enumerate(lines) if "Need help for Cancellation" in line)
    assert cancel_idx < grand_idx
    assert "Need help for Cancellation" in lines[cancel_idx]
    assert "Cancellation Request" in lines[cancel_idx]
    assert not any(line.strip() for line in lines[grand_idx + 1 :])
    # Alphabetically between Logistics and Price Mismatch under Service Task
    logistics_idx = next(i for i, line in enumerate(lines) if "Print Subs - Suspension" in line)
    price_idx = next(
        i for i, line in enumerate(lines) if i > cancel_idx and ",Price Mismatch," in line
    )
    assert logistics_idx < cancel_idx < price_idx


def test_merge_rules_json_appends_rule() -> None:
    base = '[{"id": "existing.rule", "tier": ["B2C","a","b","c","N/A"], "weight": 10.0}]'
    proposal = RuleProposal(
        proposal_id="rule.new.rule",
        kind="any_tags",
        tier=("B2C", "a", "b", "c", "N/A"),
        weight=10.5,
        support=5,
        purity=1.0,
        any_tags=("tag_x",),
    )
    merged, added = merge_rules_json(base, (proposal,))
    assert added == 1
    data = json.loads(merged)
    assert any(item["id"] == "new.rule" for item in data)


def test_confirm_promote_bumps_version(tmp_path: Path) -> None:
    live = tmp_path / "runs" / "live"
    live.mkdir(parents=True)
    (live / "Taxonomy.csv").write_text(
        "Tier1_Segment,Tier2_Stream,Tier3_Cat,Tier4_Type\nB2C,Service Task,General Support,Existing\n",
        encoding="utf-8",
    )
    (live / "classifier_rules.json").write_text("[]\n", encoding="utf-8")
    (live / "config_version.json").write_text('{"version": 2}\n', encoding="utf-8")

    rule = RuleProposal(
        proposal_id="rule.confirm.test",
        kind="any_tags",
        tier=("B2C", "Service Task", "General Support", "Existing", "N/A"),
        weight=10.0,
        support=5,
        purity=1.0,
        any_tags=("confirm_tag",),
    )
    result = confirm_learn_proposals(
        live,
        upload_id="upload-1",
        upload_filename="test.xlsx",
        rule_proposals=(rule,),
        taxonomy_proposals=(),
        accepted_rule_ids=frozenset({rule.proposal_id}),
        accepted_taxonomy_ids=frozenset(),
    )
    assert result.config_version_after == 3
    assert result.rules_added == 1
    assert read_config_version(live) == 3
    assert (live.parent / "proposals" / result.proposal_id / "manifest.json").is_file()


def test_confirm_requires_selection() -> None:
    with pytest.raises(PromoteError, match="Select at least one"):
        confirm_learn_proposals(
            Path("/tmp/unused"),
            upload_id="u",
            upload_filename="f.xlsx",
            rule_proposals=(),
            taxonomy_proposals=(),
            accepted_rule_ids=frozenset(),
            accepted_taxonomy_ids=frozenset(),
        )


def test_ensure_live_bootstrapped_copies_doc(repo_root: Path, tmp_path: Path) -> None:
    doc = repo_root / "doc" / "Taxonomy.csv"
    if not doc.is_file():
        pytest.skip("doc taxonomy missing")
    target_root = tmp_path / "proj"
    (target_root / "doc").mkdir(parents=True)
    (target_root / "doc" / "Taxonomy.csv").write_text(doc.read_text(encoding="utf-8"), encoding="utf-8")
    live = ensure_live_bootstrapped(target_root)
    assert (live / "Taxonomy.csv").is_file()
    assert (live / "classifier_rules.json").is_file()
    assert read_config_version(live) >= 1
