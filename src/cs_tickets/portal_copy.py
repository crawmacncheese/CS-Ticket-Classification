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

NAV_RULES = "Routing Rules"
RULES_PAGE_TITLE = "Routing Rules"
RULES_PAGE_INTRO = (
    "Describe routing rules in plain language. The system compiles them into "
    "classifier rules you can preview and confirm — nothing goes live until you confirm."
)
RULES_NEW_BUTTON = "Add rule"
RULES_CONFIRM_BUTTON = "Confirm live"
RULES_CONFIRM_LEAD_NOTE = (
    "Only team leads can confirm rules to live config. "
    "You can still compile and preview; ask a lead to confirm."
)
TBC_QUEUE_BUTTON = "Start manual review"
TBC_QUEUE_PAGE_TITLE = "Manual review queue"

REVIEW_CHAT_BUTTON = "Review chat"
CATEGORY_AUDIT_BUTTON = "Category audit"
CATEGORY_AUDIT_PAGE_TITLE = "Category audit"
CATEGORY_AUDIT_PAGE_INTRO = (
    "Review tickets already classified into a category bucket. "
    "Use filters or Review chat to focus on a segment (e.g. B2C cancellation) "
    "and read full ticket content."
)
CATEGORY_AUDIT_RESULTS_LINK = "← Run results"
CATEGORY_AUDIT_PREVIEW_LINK = "Ticket preview"
CATEGORY_AUDIT_SLICE_EMPTY = "No tickets match the current audit filters."
CATEGORY_AUDIT_INCLUDE_TBC_LABEL = "Include manual review (TBC)"
CATEGORY_AUDIT_TIER_LINK = "Audit"
CATEGORY_AUDIT_OPEN_SLICE = "Open audit view for this category"
CATEGORY_AUDIT_SWEEPS_HEADING = "Slice checks"
CATEGORY_AUDIT_SWEEPS_META = (
    "General hygiene checks on the current filter slice."
)
CATEGORY_AUDIT_TICKETS_HEADING = "Tickets in slice"
CATEGORY_AUDIT_CHUNK_META = "Showing {start}–{end} of {total}"
CATEGORY_AUDIT_CHUNK_PREV = "Previous"
CATEGORY_AUDIT_CHUNK_NEXT = "Next"
CATEGORY_AUDIT_RECLASSIFY_BANNER = (
    'After re-classify: <strong>{slice_label}</strong> slice {slice_before} → {slice_after} tickets '
    "(manual review {tbc_before} → {tbc_after})."
)
CATEGORY_AUDIT_RULE_LEAD_NOTE = "Only team leads can confirm rules to live config."

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
    "How many tickets landed in each category path for this run."
)

# Analyst-facing column labels for portal HTML tables (exports keep schema names).
TIER_STATS_HEADER_SEGMENT = "Segment"
TIER_STATS_HEADER_STREAM = "Stream"
TIER_STATS_HEADER_GROUP = "Category group"
TIER_STATS_HEADER_CATEGORY = "Category"
TIER_STATS_HEADER_COUNT = "Tickets"
TIER_STATS_TABLE_HEADERS = (
    TIER_STATS_HEADER_SEGMENT,
    TIER_STATS_HEADER_STREAM,
    TIER_STATS_HEADER_GROUP,
    TIER_STATS_HEADER_CATEGORY,
    TIER_STATS_HEADER_COUNT,
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

CATEGORY_FILTER_LABEL = "Category"
CATEGORY_FILTER_ALL = "All categories"
SEARCH_TICKETS_LABEL = "Search tickets"
SEARCH_TICKETS_PLACEHOLDER = "subject, body, tags"
SEGMENT_FILTER_LABEL = "Segment"
TICKET_PREVIEW_ADVANCED_SUMMARY = "More filters"
CATEGORY_FOCUS_LABEL = "Category keywords"
CATEGORY_FOCUS_PLACEHOLDER = "comma-separated"
SUBJECT_FILTER_LABEL = "Subject contains"  # legacy; merged into Search tickets
TAG_FILTER_LABEL = "Tag contains"  # legacy; merged into Search tickets
WORKBOOK_SHEETS_HINT = (
    "Workbook includes sheets <strong>Run metadata</strong>, <strong>Tickets</strong> "
    "(full rows), and <strong>Tier breakdown</strong> (category counts)."
)
TICKET_PREVIEW_CATEGORY_FILTER_META = (
    'Showing {visible} of {matched_in_slice} in "{category}" '
    "(first {limit} rows of export; {matched_total} total in run)."
)
TICKET_PREVIEW_CATEGORY_FILTER_META_FULL = (
    'Showing {visible} of {matched_total} in "{category}" (full export).'
)
TICKET_PREVIEW_NO_MATCH = "No tickets match the current filters in this preview slice."
SHOW_CLASSIFICATION_DETAILS_LABEL = "Show classification details"
CLASSIFICATION_DETAILS_LOADING = "Loading classification details…"
CLASSIFICATION_DETAILS_ERROR = "Could not load classification details."
CLASSIFICATION_DETAILS_RULES_HEADING = "Rules that fired"
CLASSIFICATION_DETAILS_CANDIDATES_HEADING = "Other candidates"
CLASSIFICATION_DETAILS_SCORE_LABEL = "Score"
CLASSIFICATION_DETAILS_MARGIN_NOTE = "Top candidates were close; assignment may be marginal."

TECHNICAL_DETAILS_SUMMARY = "How Categorization Works (Technical)"
TECHNICAL_DETAILS_BODY = """
<p>Each ticket is assigned a five-level <strong>category</strong> using tag, subject, and description signals.
Tickets the classifier cannot assign confidently go to <strong>manual review (TBC)</strong>.</p>
<p>The reference category list (allow-list) limits which categories can appear on output.
Maintainers update rules and reference categories separately from this upload flow.</p>
"""
