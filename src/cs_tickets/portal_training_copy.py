"""Analyst-facing copy for the Training portal."""

TRAINING_TITLE = "Update categories"
TRAINING_REVIEW_TITLE = "Update categories — review"
TRAINING_SUCCESS_TITLE = "Categories saved"
TRAINING_CANCEL_TITLE = "Update categories"
TRAINING_REVERT_TITLE = "Changes undone"

STEP_LABELS = ("Upload file", "Review new categories", "Preview & save")

UPLOAD_INTRO = (
    "Upload a classified workbook (<code>.xlsx</code>) to find categories "
    "that are not yet in the reference list."
)
UPLOAD_STEP_HEADING = "Upload classified workbook"
UPLOAD_BUTTON = "Upload and review"
UPLOAD_LOADING = "Uploading and parsing…"
BACK_TO_CLASSIFY_LABEL = "Back to categorize"

REVIEW_INTRO_ONE = "Found {n} new category not in the reference list."
REVIEW_INTRO_MANY = "Found {n} new categories not in the reference list."
REVIEW_STEP_HEADING = "Select categories to add"
REVIEW_HELP = (
    "Each selected category adds one example ticket and, when needed, a matching routing rule. "
    "&ldquo;Already routable&rdquo; means a rule targets that category today — "
    "the example ticket may still compete with other categories."
)

PREVIEW_STEP_HEADING = "Check impact on a ticket export (optional)"
PREVIEW_HELP = (
    "Select categories above, then upload a Zendesk export to preview how classification "
    "would change with your selection. Nothing is saved until you confirm."
)
PREVIEW_BUTTON = "Run preview"
PREVIEW_LOADING = "Running preview…"
PREVIEW_RESULTS_HEADING = "Preview results"
PREVIEW_NO_OP_LABEL = "Check which categories have no impact on this export (slower)"

SAVE_SELECTED_LABEL = "Save selected categories"
CANCEL_LABEL = "Cancel"
DONE_LABEL = "Done"
UNDO_LAST_SAVE = "Undo last save"
UNDO_FOOTNOTE = (
    "Restores the reference workbook and routing rules from your most recent save "
    "(disk only — does not undo git history)."
)

GRANULAR_VARIANT_BADGE = "Adds detail level"

VERDICT_MESSAGES: dict[str, tuple[str, str]] = {
    "strong_commit": (
        "Looks good",
        "Saving these categories should improve or maintain classification on this export.",
    ),
    "review": (
        "Review changes",
        "Some tickets would change — review the list below before saving.",
    ),
    "rules_needed": (
        "Low impact expected",
        "Many selected categories may not change any tickets on this export.",
    ),
    "risky": (
        "Caution",
        "Manual review tickets increased — talk to a classifier maintainer before saving.",
    ),
}

DESELECT_NO_OP_BUTTON = "Deselect categories with no impact"
SHOW_CHANGE_DETAILS_LABEL = "Show ticket change details"

IMPACT_COLUMN_HEADING = "Impact on export"
IMPACT_WOULD_CHANGE = "Would change tickets"
IMPACT_NO_EFFECT = "No impact"
IMPACT_NOT_ANALYZED = "Not in last preview"
IMPACT_SUMMARY = (
    "On this export: {impactful} would change tickets, {no_op} have no impact "
    "(of {total} in your last preview)."
)
