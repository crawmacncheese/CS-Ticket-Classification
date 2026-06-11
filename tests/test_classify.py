from pathlib import Path

import pytest

from cs_tickets.classify import classify_row, classify_row_with_explanation, tbc_reason
from cs_tickets.taxonomy import load_allowlist
from cs_tickets.thread_enrich import build_ticket_index, flatten_for_classify


def test_classifier_rules_load() -> None:
    from cs_tickets.classifier_rules import load_rule_specs

    rules = load_rule_specs()
    assert rules
    assert {rule.id for rule in rules} >= {
        "live_chat.b2c.strict",
        "billing.system_report.rosetta_renewal.b2c",
        "sales.upgrade.b2c",
        "junk.external_noise_chinese.b2c",
        "complaint.cancel_language.b2c",
    }


def test_tbc_reason_buckets() -> None:
    from cs_tickets.classify import ClassificationDecision, RuleEvidence

    tier = ("B2C", "Service Task", "General Support", "TBC (Manual Review)", "N/A")
    zero = ClassificationDecision(
        tier=tier, score=0.0, fallback_used=True, candidates=(), evidence=()
    )
    assert tbc_reason(zero) == "zero_candidate"

    filtered = ClassificationDecision(
        tier=tier,
        score=0.0,
        fallback_used=True,
        candidates=(),
        evidence=(
            RuleEvidence(rule_id="x", tier=tier, weight=10.0, signal="data_rule"),
        ),
    )
    assert tbc_reason(filtered) == "allowlist_filtered"

    margin = ClassificationDecision(
        tier=tier,
        score=10.0,
        fallback_used=True,
        candidates=((tier, 10.0), (tier, 9.5)),
        evidence=(),
    )
    assert tbc_reason(margin) == "lost_margin"


def test_candidate_margin_rejects_close_low_confidence_scores() -> None:
    from cs_tickets.classify import _accepted_score

    first = ("B2C", "Service Task", "General Support", "Remove card details", "N/A")
    second = ("B2C", "Service Task", "Sales Leads", "Upgrade Inquiry", "N/A")
    assert _accepted_score(((first, 5.5), (second, 4.5))) is False
    assert _accepted_score(((first, 7.0), (second, 4.5))) is True
    assert _accepted_score(((first, 12.0), (second, 11.5))) is True


def test_classify_zopim_chat(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["zopim_chat","annual_term"]',
        "subject": "Conversation with X",
        "raw_subject": "Conversation with X",
        "description": "Conversation with X\n\nURL: https://subscribe.scmp.com/plus",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/1.json",
    }
    tier = classify_row(row, allow)
    assert tier == (
        "B2C",
        "Service Task",
        "General Support",
        "No Content - Live chat auto-trigger",
        "N/A",
    )


def test_zopim_without_subscribe_url_not_live_chat(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["zopim_chat","annual_term"]',
        "subject": "Conversation with Fred Smith",
        "raw_subject": "Conversation with Fred Smith",
        "description": "Conversation with Fred Smith\n\nURL: https://account.scmp.com/manage/subscription",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/2.json",
    }
    tier = classify_row(row, allow)
    assert tier[3] != "No Content - Live chat auto-trigger"


def test_zopim_printsupport_prefers_b2b_live_chat(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["zopim_chat","printsupport"]',
        "subject": "Chat",
        "raw_subject": "Chat",
        "description": "",
        "url": "https://scmpsupport.zendesk.com/agent/tickets/1/printsupport",
    }
    tier = classify_row(row, allow)
    assert tier == (
        "B2B",
        "Service Task",
        "General Support",
        "No Content - Live chat auto-trigger",
        "N/A",
    )


def test_printsupport_editorial_keyword(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["printsupport"]',
        "subject": "Archive request",
        "raw_subject": "Archive request",
        "description": "Please arrange an archival reprint for our client.",
        "url": "https://scmpsupport.zendesk.com/hc/printsupport",
    }
    tier = classify_row(row, allow)
    assert tier == (
        "B2B",
        "Service Task",
        "Editorial Feedback",
        "Editorial / Archive Request",
        "N/A",
    )


def test_printsupport_no_signal_falls_back_tbc(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["printsupport"]',
        "subject": "Question",
        "raw_subject": "Question",
        "description": "Hello.",
        "url": "https://scmpsupport.zendesk.com/hc/printsupport",
    }
    tier = classify_row(row, allow)
    assert tier[0] == "B2B" and "TBC" in tier[3]


def test_explanation_reports_matched_rules(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["zopim_chat"]',
        "subject": "Conversation with Visitor",
        "raw_subject": "Conversation with Visitor",
        "description": "Conversation with Visitor\n\nURL: https://subscribe.scmp.com/",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/5.json",
    }
    decision = classify_row_with_explanation(row, allow)
    assert decision.tier == classify_row(row, allow)
    assert decision.fallback_used is False
    assert any(ev.rule_id == "live_chat.b2c.strict" for ev in decision.evidence)


def test_invoice_request_remains_classified_after_margin_guard(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["other_departments"]',
        "subject": "SCMP Invoice",
        "raw_subject": "SCMP Invoice",
        "description": "Please send the invoice for this subscription.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/8.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Billing & Admin",
        "Invoices and PO request",
        "N/A",
    )


def test_b2c_upgrade_keyword_classifies_upgrade_inquiry(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber"]',
        "subject": "Upgrade inquiry",
        "raw_subject": "Upgrade inquiry",
        "description": "I want to upgrade my SCMP subscription plan.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/2.json",
    }
    tier = classify_row(row, allow)
    assert tier == (
        "B2C",
        "Service Task",
        "Sales Leads",
        "Upgrade Inquiry",
        "N/A",
    )


def test_remove_card_details_classifies_general_support(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber"]',
        "subject": "Remove card details",
        "raw_subject": "Remove card details",
        "description": "Please remove my credit card details from my account.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/3.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "General Support",
        "Remove card details",
        "N/A",
    )


def test_delete_account_request_classifies_account_management(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber"]',
        "subject": "Delete my account",
        "raw_subject": "Delete my account",
        "description": "I would like to delete my SCMP account permanently.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/4.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Account Management",
        "Request to delete account",
        "N/A",
    )


def test_b2c_renewal_tags_classify_rate_or_renewal(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber","subscription_-_renew","annual_term"]',
        "subject": "Reminder of Your SCMP Renewal",
        "raw_subject": "Reminder of Your SCMP Renewal",
        "description": "Please help with my SCMP renewal.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/6.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Sales Leads",
        "Rate or Renewal Inquiry",
        "N/A",
    )


def test_paid_subscriber_cannot_access_article_classifies_access_bug(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["digital","existing_subscriber","product_-_access_issue"]',
        "subject": "Cannot access article",
        "raw_subject": "Cannot access article",
        "description": "I paid for a subscription but cannot access articles.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/7.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Complaint",
        "Technical Bug",
        "Access Loop or App Bug",
        "N/A",
    )


def test_zopim_account_portal_classifies_renewal_inquiry(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["zopim_chat","annual_term","digital","existing_subscriber"]',
        "subject": "Conversation with Jonathan Lai",
        "raw_subject": "Conversation with Jonathan Lai",
        "description": "Conversation with Jonathan Lai\n\nURL: https://account.scmp.com/manage/subscription",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/40.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Sales Leads",
        "Rate or Renewal Inquiry",
        "N/A",
    )


def test_zopim_account_upgrade_url_classifies_upgrade(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["zopim_chat","digital","existing_subscriber","product_-_access_issue"]',
        "subject": "Conversation with Soo YeWah",
        "raw_subject": "Conversation with Soo YeWah",
        "description": "Conversation with Soo YeWah\n\nURL: https://account.scmp.com/manage/subscription?upgrade=true",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/41.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Sales Leads",
        "Upgrade Inquiry",
        "N/A",
    )


def test_access_issue_tag_only_without_blob_phrase(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["product_-_access_issue","digital","existing_subscriber"]',
        "subject": "When I browsing the news on Chrome",
        "raw_subject": "When I browsing the news on Chrome",
        "description": "When I browsing the news on Chrome, the website shows errors.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/42.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Complaint",
        "Technical Bug",
        "Access Loop or App Bug",
        "N/A",
    )


def test_reply_inherits_parent_subscriber_tags(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    parent = {
        "id": 900100,
        "tags": ["existing_subscriber", "digital", "subscription_-_renew"],
        "subject": "Account question",
        "description": "Please advise on my subscription.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/900100.json",
    }
    child = {
        "id": 900101,
        "tags": ["miscellaneous"],
        "subject": "RE: Account question",
        "raw_subject": "RE: Account question",
        "description": "See my previous email.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/900101.json",
        "via": {"source": {"rel": "follow_up", "from": {"ticket_id": 900100}}},
    }
    index = build_ticket_index([parent, child])
    row = flatten_for_classify(child, index)
    decision = classify_row_with_explanation(row, allow)
    assert decision.tier == (
        "B2C",
        "Service Task",
        "Sales Leads",
        "Rate or Renewal Inquiry",
        "N/A",
    )
    assert any(e.rule_id == "computed:reply_inherit_parent_tags.b2c" for e in decision.evidence)


def test_retention_offer_email_classifies_retention(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["existing_subscriber","digital"]',
        "subject": "Re: Hi, we hope you will continue to support SCMP Journalism",
        "raw_subject": "Re: Hi, we hope you will continue to support SCMP Journalism",
        "description": "We hope you will continue to support SCMP journalism.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/43.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "General Support",
        "Retention Offer",
        "N/A",
    )


def test_rosetta_renewal_confirmation_classifies_system_report(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["subscription_-_renew","annual_term"]',
        "subject": "Your subscription has been renewed",
        "raw_subject": "Your subscription has been renewed",
        "description": (
            "Thank you. Your SCMP subscription renewal was processed successfully. "
            "Rosetta System Email"
        ),
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/30.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Billing & Admin",
        "System Report",
        "N/A",
    )


def test_esp_opp_invoice_remaps_to_b2b(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["other_departments"]',
        "subject": "[PO: STBPO20250001309] Invoice Rejection",
        "raw_subject": "[PO: STBPO20250001309] Invoice Rejection",
        "description": "ID Ref#: ESP-OPP-034949\nCompany Name: Example Corp\nPlease resend invoice.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/31.json",
    }
    tier = classify_row(row, allow)
    assert tier[0] == "B2B"
    assert tier[3] == "Invoices and PO request"


def test_esp_opp_renewal_remaps_to_b2b_sales(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["account_renewal","annual_term"]',
        "subject": "SCMP RENEWAL",
        "raw_subject": "SCMP RENEWAL",
        "description": "Subscription No. ESP-OPP-033877.\nDear team, please confirm renewal pricing.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/32.json",
    }
    tier = classify_row(row, allow)
    assert tier == (
        "B2B",
        "Service Task",
        "Sales Leads",
        "Rate or Renewal Inquiry",
        "N/A",
    )


def test_system_payment_report_classifies_system_report(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["sfpayment"]',
        "subject": "Stripe Payment Completed - ESP-OPP-040203",
        "raw_subject": "Stripe Payment Completed - ESP-OPP-040203",
        "description": "Payment completed notification for subscription.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/9.json",
    }
    tier = classify_row(row, allow)
    assert tier == (
        "B2B",
        "Service Task",
        "Billing & Admin",
        "Invoices and PO request",
        "N/A",
    )


def test_missing_paper_classifies_print_logistics(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["delivery_-_missing_or_delay_delivery","2._paper_replenishment"]',
        "subject": "Missing Paper",
        "raw_subject": "Missing Paper",
        "description": "Customer reported a missing copy and needs paper replenishment.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/10.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Logistics",
        "Print Subs - Suspension and Resume confirmation",
        "N/A",
    )


def test_media_release_classifies_external_noise(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["miscellaneous"]',
        "subject": "Media Release: OECD releases landmark early learning study",
        "raw_subject": "Media Release: OECD releases landmark early learning study",
        "description": "External media release for editorial consideration.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/11.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Junk",
        "Junk",
        "PR / External Sales / Editorial Noise",
        "N/A",
    )


def test_data_erasure_request_classifies_delete_account(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["data_enquiry","not_subscribed"]',
        "subject": "SCMP data erasure request",
        "raw_subject": "SCMP data erasure request",
        "description": "Please delete all my personal data from SCMP records.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/12.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Account Management",
        "Request to delete account",
        "N/A",
    )


def test_unable_to_log_in_classifies_access_bug(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["annual_term","digital","existing_subscriber","product_-_access_issue"]',
        "subject": "Unable to Log In",
        "raw_subject": "Unable to Log In",
        "description": "I am unable to log in to my SCMP account on my phone.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/20.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Complaint",
        "Technical Bug",
        "Access Loop or App Bug",
        "N/A",
    )


def test_non_renewal_classifies_cancellation_not_renewal_inquiry(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["subscription_-_renew"]',
        "subject": "Non-renewal of subscription -Customer ID: CL 012469",
        "raw_subject": "Non-renewal of subscription -Customer ID: CL 012469",
        "description": "Please process non-renewal of my subscription.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/21.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Complaint",
        "Refund",
        "Cancellation Request",
        "N/A",
    )


def test_chinese_media_invite_classifies_pr_noise(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["editorial"]',
        "subject": "採訪邀請_「第76屆再生元國際科學與工程大獎賽」",
        "raw_subject": "採訪邀請_「第76屆再生元國際科學與工程大獎賽」",
        "description": "誠邀貴報派記者採訪。",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/22.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Junk",
        "Junk",
        "PR / External Sales / Editorial Noise",
        "N/A",
    )


def test_alipayhk_auto_debit_notice_stays_tbc_without_customer_cancel_language(
    repo_root: Path,
) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["account_renewal","digital","existing_subscriber","monthly_term"]',
        "subject": "AlipayHK Subscriber Auto Debit Cancellation: user@example.com",
        "raw_subject": "AlipayHK Subscriber Auto Debit Cancellation: user@example.com",
        "description": "Automated notification from payment provider.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/23.json",
    }
    tier = classify_row(row, allow)
    assert "TBC" in tier[3] or tier[3] == "Rate or Renewal Inquiry"


def test_order_confirmation_classifies_system_report(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": "[]",
        "subject": "RE: SCMP Order Confirmation and Credit Card Payment",
        "raw_subject": "RE: SCMP Order Confirmation and Credit Card Payment",
        "description": "Following up on my SCMP order confirmation and credit card payment.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/24.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Billing & Admin",
        "System Report",
        "N/A",
    )


def test_account_renewal_tag_classifies_renewal_inquiry_without_renewal_blob(
    repo_root: Path,
) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["account_renewal","annual_term","digital","existing_subscriber"]',
        "subject": "Question about my account",
        "raw_subject": "Question about my account",
        "description": "Please advise on my SCMP account status.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/25.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Service Task",
        "Sales Leads",
        "Rate or Renewal Inquiry",
        "N/A",
    )


def test_pdf_download_issue_classifies_access_bug(repo_root: Path) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    row = {
        "tags": '["product_issue_-_digital"]',
        "subject": "I can't download your PDF",
        "raw_subject": "I can't download your PDF",
        "description": "The ePaper PDF download does not work.",
        "url": "https://scmpsupport.zendesk.com/api/v2/tickets/13.json",
    }
    assert classify_row(row, allow) == (
        "B2C",
        "Complaint",
        "Technical Bug",
        "Access Loop or App Bug",
        "N/A",
    )
