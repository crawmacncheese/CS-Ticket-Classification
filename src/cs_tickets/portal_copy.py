"""Analyst-facing copy for the classify portal (plain language per CONTEXT.md)."""

CLASSIFY_PAGE_TITLE = "Categorize support tickets"
CLASSIFY_PAGE_INTRO = (
    "Upload your Zendesk ticket export (<code>.json</code> or <code>.ndjson</code>). "
    "After the run you will see how many tickets need manual review, a category breakdown, "
    "and a preview table."
)
CLASSIFY_RUN_BUTTON = "Categorize tickets"
CLASSIFY_RUN_LOADING = "Categorizing…"
CLASSIFY_BAD_CSAT_LABEL = "Only categorize tickets with bad CSAT rating"

TRAINING_LINK_LABEL = "Update reference categories"
TRAINING_LINK_HINT = "Upload a classified workbook to add new categories to the reference list."

CATEGORY_BREAKDOWN_HEADING = "Category breakdown"
CATEGORY_BREAKDOWN_META = "Counts by category path (Tier1–Tier4) for this run."
TICKET_PREVIEW_HEADING = "Ticket preview"
DOWNLOAD_WORKBOOK_LABEL = "Download Excel workbook"
NEW_UPLOAD_LABEL = "New upload"

TECHNICAL_DETAILS_SUMMARY = "How categorization works (technical)"
TECHNICAL_DETAILS_BODY = """
<p>Each ticket is assigned a five-level <strong>category</strong> using tag, subject, and description signals.
Tickets the classifier cannot assign confidently go to <strong>manual review (TBC)</strong>.</p>
<p>The reference category list (allow-list) limits which categories can appear on output.
Maintainers update rules and reference categories separately from this upload flow.</p>
"""
