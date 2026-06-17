from cs_tickets.feedback.models import RuleProposal, TaxonomyProposal
from cs_tickets.portal_learn import (
    learn_proposals_html,
    learn_preview_results_html,
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
    assert "learn-preview-details" not in html


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


def test_learn_impact_column_and_deselect_after_no_op_preview() -> None:
    from cs_tickets.feedback.parse import LearnParseResult

    no_op_tier = ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A")
    impactful_tier = ("B2B", "Other Stream", "Other Cat", "Other Type", "N/A")
    rule_no_op = RuleProposal(
        proposal_id="rule.no_op",
        kind="any_tags",
        tier=no_op_tier,
        weight=10.0,
        support=5,
        purity=1.0,
        any_tags=("noop_tag",),
    )
    rule_impact = RuleProposal(
        proposal_id="rule.impact",
        kind="any_tags",
        tier=impactful_tier,
        weight=10.0,
        support=6,
        purity=1.0,
        any_tags=("impact_tag",),
    )
    preview_rules = frozenset({rule_no_op.proposal_id, rule_impact.proposal_id})
    html = learn_proposals_html(
        LearnParseResult(
            upload_id="u",
            filename="f.xlsx",
            row_count=10,
            eligible_row_count=10,
            distinct_tier_paths=2,
            rule_proposal_count=2,
            taxonomy_proposal_count=0,
            rule_proposals=(rule_no_op, rule_impact),
        ),
        "upload-123",
        status="processed",
        checked_rule_ids=preview_rules,
        show_impact=True,
        preview_rule_ids=preview_rules,
        preview_tax_ids=frozenset(),
        no_op_tuples=frozenset({no_op_tier}),
    )
    assert "Impact on export" in html
    assert "Would change tickets" in html
    assert "No impact" in html
    assert "learn-deselect-no-op-btn" in html
    assert 'data-checkbox-name="rule_ids"' in html
    assert 'learn-deselect-no-op-btn" data-checkbox-name="tax_ids"' not in html
    assert "deselect-no-op-tuples" not in html
    assert 'learn-row--no-op' in html
    assert "1 would change tickets, 1 have no impact" in html
    assert "show-changed-details" not in html


def test_learn_taxonomy_deselect_button_only_on_tax_section() -> None:
    from cs_tickets.feedback.parse import LearnParseResult

    no_op_tier = ("B2C", "Service Task", "General Support", "New Type", "N/A")
    tax = TaxonomyProposal(
        proposal_id="tax.no_op",
        tier=no_op_tier,
        count=3,
        novelty_type="tier4_new",
        evidence_ids=("1",),
    )
    preview_tax = frozenset({tax.proposal_id})
    html = learn_proposals_html(
        LearnParseResult(
            upload_id="u",
            filename="f.xlsx",
            row_count=10,
            eligible_row_count=10,
            distinct_tier_paths=1,
            rule_proposal_count=0,
            taxonomy_proposal_count=1,
            taxonomy_proposals=(tax,),
        ),
        "upload-123",
        status="processed",
        checked_tax_ids=preview_tax,
        show_impact=True,
        preview_rule_ids=frozenset(),
        preview_tax_ids=preview_tax,
        no_op_tuples=frozenset({no_op_tier}),
    )
    assert 'learn-deselect-no-op-btn" data-checkbox-name="tax_ids"' in html
    assert 'learn-deselect-no-op-btn" data-checkbox-name="rule_ids"' not in html


def test_learn_show_changed_details_in_preview_results() -> None:
    from cs_tickets.allowlist_compare import AllowlistCompareResult

    compare = AllowlistCompareResult(
        total=1,
        tbc_old=1,
        tbc_new=0,
        changed_rows=[
            {
                "id": "101",
                "old_tier4": "Old",
                "new_tier4": "New",
                "outcome_type": "gap_fix",
                "gap_fix_mechanism": "rule",
                "new_tbc_reason": "matched",
            }
        ],
        zero_candidate_old=0,
        zero_candidate_new=0,
    )
    html = learn_preview_results_html(compare_result=compare)
    assert "show-changed-details" in html
    assert "training-changed-table" in html
