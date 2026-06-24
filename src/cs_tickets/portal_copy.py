"""Analyst-facing copy for the classify portal (plain language per CONTEXT.md)."""

CLASSIFY_PAGE_TITLE = "Categorize Support Tickets"
CLASSIFY_PAGE_INTRO = (
    "Upload a Zendesk export (<code>.json</code> or <code>.ndjson</code>). "
    "You will see how many tickets need a person to review, a breakdown by category, "
    "and a sample of the results."
)
CLASSIFY_RUN_BUTTON = "Categorize Tickets"
CLASSIFY_RUN_LOADING = "Categorizing…"
CLASSIFY_BAD_CSAT_LABEL = "Only Include Tickets With a Bad CSAT Rating"

TRAINING_LINK_LABEL = "Add New Categories"
TRAINING_LINK_HINT = (
    "Upload a categorized workbook to suggest new categories for the reference list."
)

NAV_CATEGORIZE = "Categorize Tickets"
NAV_REFERENCE_CATEGORIES = TRAINING_LINK_LABEL
NAV_TBC_TRENDS = "Manual Review Trends"
NAV_RUN_HISTORY = "Run History"

REFERENCE_CATEGORIES_PAGE_TITLE = TRAINING_LINK_LABEL
REFERENCE_CATEGORIES_PAGE_INTRO = (
    "Upload the team's categorized Excel workbook "
    "(<code>SCMP_Tickets_Master_Categorized</code>). "
    "We will suggest new categories and routing rules. "
    "Nothing goes live until you review and confirm."
)

LEARN_PROCESS_BUTTON = "Analyze Workbook"
LEARN_UPLOAD_ANOTHER_LABEL = "Upload Another Workbook"
LEARN_TRY_AGAIN_LABEL = "Try Again"
LEARN_CONFIRM_BUTTON = "Confirm Changes"
LEARN_CONFIRM_HELP = (
    "Confirmed changes apply to the <strong>next categorization run</strong> "
    "(config version will increase)."
)
LEARN_SUGGESTED_RULES_HEADING = "Suggested Rules"
LEARN_SUGGESTED_RULES_META = (
    "When a ticket matches the description, assign it to the category shown."
)
LEARN_NEW_CATEGORY_PATHS_HEADING = "New Category Paths"
LEARN_NEW_CATEGORY_PATHS_META = (
    "These category combinations appear in your upload but are not in the current list."
)
LEARN_CHANGED_TICKETS_HEADING = "Changed Tickets"
LEARN_UNDO_LAST_CONFIRM = "Undo Last Confirm"
LEARN_UNDO_NOTE = (
    "Restores the previous live settings (category list and routing rules)."
)

CATEGORY_BREAKDOWN_HEADING = "Results By Category"
CATEGORY_BREAKDOWN_META = (
    "How many tickets landed in each category path (Tier 1–Tier 4) for this run."
)
TICKET_PREVIEW_HEADING = "Ticket Preview"
DOWNLOAD_WORKBOOK_LABEL = "Download Excel Workbook"
NEW_UPLOAD_LABEL = "Upload Another File"

TBC_REASON_LABELS: dict[str, str] = {
    "zero_candidate": "No rules matched",
    "allowlist_filtered": "Rules blocked",
    "below_threshold": "Weak signal",
    "lost_margin": "Contested",
    "other": "Other",
}

TBC_REASON_EXPLANATIONS: dict[str, str] = {
    "zero_candidate": "No classification rules fired or accumulated a score.",
    "allowlist_filtered": "Rules matched but every target category is outside the allow-list.",
    "below_threshold": "Best candidate score was below the confidence threshold.",
    "lost_margin": "Top candidates were too close to call confidently.",
    "other": "Manual review for another scoring reason.",
}

TBC_REASON_DISPLAY_BUCKETS = (
    "zero_candidate",
    "allowlist_filtered",
    "below_threshold",
    "lost_margin",
    "other",
)

SHOW_TICKET_PREVIEW_DETAILS_LABEL = "Show ticket details"
SHOW_TICKET_PREVIEW_TBC_ONLY_LABEL = "Show manual review (TBC) only"
TICKET_PREVIEW_SELECT_HINT = "Select a ticket above to view its content."
TICKET_PREVIEW_TBC_FILTER_META = (
    "Showing {visible} of {tbc_in_slice} manual review tickets in this preview "
    "(first {limit} rows of export)."
)
TICKET_PREVIEW_CAP_META = "First {shown} rows of the export (preview cap {limit})."
TBC_REASON_SUMMARY_HEADING = "Why tickets need manual review"

TECHNICAL_DETAILS_SUMMARY = "How Categorization Works (Technical)"
TECHNICAL_DETAILS_BODY = """
<p>Each ticket is assigned a five-level <strong>category</strong> using tag, subject, and description signals.
Tickets the classifier cannot assign confidently go to <strong>manual review (TBC)</strong>.</p>
<p>The reference category list (allow-list) limits which categories can appear on output.
Maintainers update rules and reference categories separately from this upload flow.</p>
"""
