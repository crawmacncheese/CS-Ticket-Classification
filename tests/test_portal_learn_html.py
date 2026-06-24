from cs_tickets.feedback.models import RuleProposal, TaxonomyProposal
from cs_tickets.portal_learn import (
    learn_proposals_html,
    match_consistency_plain,
    novelty_plain,
    rule_proposals_table_html,
    rule_trigger_plain,
    taxonomy_proposals_table_html,
)


def test_rule_trigger_plain_any_tags() -> None:
    p = RuleProposal(
        proposal_id="x",
        kind="any_tags",
        tier=("B2C", "Service Task", "Sales Leads", "Upgrade Inquiry", "N/A"),
        weight=11.0,
        support=10,
        purity=0.95,
        any_tags=("subscription_-_pricing",),
    )
    assert rule_trigger_plain(p) == "Tagged with: subscription_-_pricing"


def test_rule_trigger_plain_all_tags() -> None:
    p = RuleProposal(
        proposal_id="x",
        kind="all_tags",
        tier=("B2C", "Service Task", "Sales Leads", "Upgrade Inquiry", "N/A"),
        weight=11.0,
        support=10,
        purity=1.0,
        all_tags=("zopim_chat", "new_subscriber"),
    )
    assert "Tagged with all of:" in rule_trigger_plain(p)
    assert "zopim_chat" in rule_trigger_plain(p)


def test_match_consistency_plain() -> None:
    perfect = RuleProposal(
        proposal_id="x",
        kind="any_tags",
        tier=("B2C", "a", "b", "c", "N/A"),
        weight=10.0,
        support=5,
        purity=1.0,
        any_tags=("tag",),
    )
    assert match_consistency_plain(perfect) == "All same category"

    mixed = RuleProposal(
        proposal_id="y",
        kind="any_tags",
        tier=("B2C", "a", "b", "c", "N/A"),
        weight=10.0,
        support=20,
        purity=0.9,
        any_tags=("tag",),
    )
    assert match_consistency_plain(mixed) == "90% same category"


def test_rule_table_uses_stats_table_and_cs_headers() -> None:
    p = RuleProposal(
        proposal_id="rule.any_tags.test",
        kind="any_tags",
        tier=("B2C", "Service Task", "General Support", "Login Issue", "N/A"),
        weight=12.0,
        support=8,
        purity=1.0,
        any_tags=("login_issue",),
        evidence_ids=("101", "102"),
    )
    html = rule_proposals_table_html((p,))
    assert 'class="stats-table"' in html
    assert "When tickets…" in html
    assert "Tier1_Segment" in html
    assert "COUNTA of id" in html
    assert "Tagged with: login_issue" in html
    assert "Login Issue" in html
    assert "any_tags" not in html
    assert "proposal_id" not in html


def test_rule_table_formats_float_evidence_ids() -> None:
    p = RuleProposal(
        proposal_id="rule.any_tags.test",
        kind="any_tags",
        tier=("B2C", "Service Task", "General Support", "Login Issue", "N/A"),
        weight=12.0,
        support=8,
        purity=1.0,
        any_tags=("login_issue",),
        evidence_ids=("168595.0", "168596.0", "168607.0", "168608.0", "168609.0"),
    )
    html = rule_proposals_table_html((p,))
    assert "168595, 168596, 168607 (+2 more)" in html
    assert "168595.0" not in html


def test_taxonomy_table_pivot_blanks_and_cs_labels() -> None:
    proposals = (
        TaxonomyProposal(
            proposal_id="tax.a",
            tier=("B2C", "Service Task", "General Support", "Type A", "N/A"),
            count=3,
            novelty_type="tier4_new",
            evidence_ids=("1",),
        ),
        TaxonomyProposal(
            proposal_id="tax.b",
            tier=("B2C", "Service Task", "General Support", "Type B", "N/A"),
            count=2,
            novelty_type="tier4_new",
            evidence_ids=("2",),
        ),
    )
    html = taxonomy_proposals_table_html(proposals)
    assert 'class="stats-table"' in html
    assert "What's new" in html
    assert "New Tier 4 type" in html
    assert novelty_plain(proposals[0]) == "New Tier 4 type"


def test_learn_proposals_html_empty_message() -> None:
    from cs_tickets.feedback.parse import LearnParseResult

    html = learn_proposals_html(
        LearnParseResult(
            upload_id="u",
            filename="f.xlsx",
            row_count=0,
            eligible_row_count=0,
            distinct_tier_paths=0,
            rule_proposal_count=0,
            taxonomy_proposal_count=0,
        ),
        "upload-id",
    )
    assert "No suggestions met" in html
    assert "stats-table" not in html


def test_learn_proposals_html_has_confirm_form() -> None:
    from cs_tickets.feedback.models import RuleProposal
    from cs_tickets.feedback.parse import LearnParseResult

    proposal = RuleProposal(
        proposal_id="rule.test",
        kind="any_tags",
        tier=("B2C", "Service Task", "General Support", "Login Issue", "N/A"),
        weight=10.0,
        support=5,
        purity=1.0,
        any_tags=("tag",),
    )
    html = learn_proposals_html(
        LearnParseResult(
            upload_id="u",
            filename="f.xlsx",
            row_count=10,
            eligible_row_count=10,
            distinct_tier_paths=1,
            rule_proposal_count=1,
            taxonomy_proposal_count=0,
            rule_proposals=(proposal,),
        ),
        "upload-123",
        status="processed",
    )
    assert 'id="learn-confirm-form"' in html
    assert 'name="rule_ids"' in html
    assert "Select all" in html
    assert "learn-select-all-btn" in html
    assert "Confirm changes" not in html


def test_learn_process_body_orders_preview_before_confirm() -> None:
    from cs_tickets.feedback.models import RuleProposal
    from cs_tickets.feedback.parse import LearnParseResult
    from cs_tickets.portal_learn import learn_process_body_html

    proposal = RuleProposal(
        proposal_id="rule.test",
        kind="any_tags",
        tier=("B2C", "Service Task", "General Support", "Login Issue", "N/A"),
        weight=10.0,
        support=5,
        purity=1.0,
        any_tags=("tag",),
    )
    result = LearnParseResult(
        upload_id="u",
        filename="f.xlsx",
        row_count=10,
        eligible_row_count=10,
        distinct_tier_paths=1,
        rule_proposal_count=1,
        taxonomy_proposal_count=0,
        rule_proposals=(proposal,),
    )
    html = learn_process_body_html(result, "upload-123")
    preview_pos = html.index("learn-preview-section")
    confirm_pos = html.index("Confirm changes")
    assert preview_pos < confirm_pos
    assert "Cancel" in html
    assert 'class="learn-preview-details"' in html
    assert "Preview is not required" in html
    assert "First time updating categories" in html


def test_selectable_tables_include_select_all_for_rules_and_taxonomy() -> None:
    from cs_tickets.feedback.models import RuleProposal
    from cs_tickets.feedback.parse import LearnParseResult

    rule = RuleProposal(
        proposal_id="rule.test",
        kind="any_tags",
        tier=("B2C", "Service Task", "General Support", "Login Issue", "N/A"),
        weight=10.0,
        support=5,
        purity=1.0,
        any_tags=("tag",),
    )
    tax = TaxonomyProposal(
        proposal_id="tax.test",
        tier=("B2C", "Service Task", "General Support", "New Type", "N/A"),
        count=3,
        novelty_type="tier4_new",
        evidence_ids=("1",),
    )
    html = learn_proposals_html(
        LearnParseResult(
            upload_id="u",
            filename="f.xlsx",
            row_count=10,
            eligible_row_count=10,
            distinct_tier_paths=2,
            rule_proposal_count=1,
            taxonomy_proposal_count=1,
            rule_proposals=(rule,),
            taxonomy_proposals=(tax,),
        ),
        "upload-123",
        status="processed",
    )
    assert html.count("learn-select-all-btn") == 2
    assert 'data-checkbox-name="rule_ids"' in html
    assert 'data-checkbox-name="tax_ids"' in html
    assert 'class="learn-row-chk"' in html
    assert "learn-select-all-btn" in html
