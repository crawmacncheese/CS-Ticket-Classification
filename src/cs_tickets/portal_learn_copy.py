"""Analyst-facing copy for the Learn (/learn) portal flow."""

LEARN_STEP_LABELS = (
    "Upload workbook",
    "Review suggestions",
    "Check impact (optional)",
    "Confirm",
)

PREVIEW_DETAILS_SUMMARY = "Preview: see how this affects real tickets"
SESSION_DETAILS_SUMMARY = "Session details"
PREVIEW_STEP_HEADING = "Check impact on a ticket export (optional)"
PREVIEW_HELP = (
    "Upload a recent Zendesk ticket export to see how your selected rules and "
    "category paths would change classification. Nothing goes live until you confirm."
)
PREVIEW_BUTTON = "Run preview"
PREVIEW_LOADING = "Running preview…"
PREVIEW_RESULTS_HEADING = "Preview results"
PREVIEW_NO_OP_LABEL = "Show which selections have no impact on this export (slower)"
PREVIEW_NO_OP_HINT = (
    "Unsure whether your selections matter? Turn this on to see which rows "
    "would actually change tickets."
)
PREVIEW_NO_OP_RULES_NEEDED_HINT = (
    "Enable “check no impact” above and re-run preview to see which rows to deselect."
)

PREVIEW_FILE_LABEL = "Ticket export (.json or .ndjson)"
PREVIEW_FILE_STEP_2 = "Select the rules and category paths you want above."
PREVIEW_FILE_STEP_3 = "Upload that file here and click Run preview."

TBC_FOOTNOTE = "TBC = tickets the classifier sends to manual review."

RULES_TABLE_SUMMARY = "Suggested rules ({n})"
TAXONOMY_TABLE_SUMMARY = "New category paths ({n})"
METRICS_TABLE_SUMMARY = "Preview metrics"
CHANGED_TICKETS_SUMMARY = "Changed tickets ({n})"

PREVIEW_SKIP_NOTE = (
    "Preview is not required. If you trust the labels in your workbook, "
    "you can confirm below — changes apply on the next categorization run."
)
PREVIEW_FIRST_TIME_NUDGE = (
    "First time updating categories? We recommend expanding preview above and "
    "using a recent ticket export."
)

RULES_SECTION_INTRO = (
    "Suggested rules are patterns the classifier will use to auto-tag similar tickets. "
    "When a ticket matches the description, it is assigned to the category shown."
)
TAXONOMY_SECTION_INTRO = (
    "New category paths are tier combinations from your upload that are not in the "
    "current reference list. Preview simulates rules and category paths together."
)

CONFIRM_APPLIES_NOTE = (
    "Confirm applies to the <strong>next categorization run</strong> immediately "
    "(config version will increment)."
)

CANCEL_LABEL = "Cancel"

VERDICT_NEXT_STEPS: dict[str, str] = {
    "strong_commit": (
        "You can confirm — these changes should help or maintain categorization on this export."
    ),
    "review": "Check the changed tickets below, then confirm if they look right.",
    "rules_needed": (
        "Many selections may not affect this export — deselect no-impact rows or confirm anyway."
    ),
    "risky": "Manual review tickets increased — talk to a classifier maintainer before confirming.",
}

VERDICT_STAT_LABELS: dict[str, str] = {
    "gap_fix": "Auto-categorized",
    "regression": "More manual review",
    "reroute": "Reclassified",
}

STALE_PREVIEW_CONFIRM_WARNING = (
    "Your preview is out of date — re-run preview or confirm at your own risk."
)

CONFIRM_DIALOG_LEAD = "Confirm {n_rules} rules and {n_tax} category paths?"
CONFIRM_DIALOG_SUFFIX = "Changes apply on the next categorization run."

CONFIRM_RISKY_WARNING = (
    "Preview showed increased manual review tickets. Talk to a classifier maintainer "
    "before confirming. Continue anyway?"
)
