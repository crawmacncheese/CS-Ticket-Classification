"""Analyst-facing copy for the Training portal."""

TRAINING_TITLE = "Update Categories"
TRAINING_REVIEW_TITLE = "Update Categories — Review"
TRAINING_SUCCESS_TITLE = "Categories Saved"
TRAINING_CANCEL_TITLE = "Update Categories"
TRAINING_REVERT_TITLE = "Changes Undone"

STEP_LABELS = ("Upload File", "Review New Categories", "Preview And Save")

UPLOAD_INTRO = (
    "Upload a classified workbook (<code>.xlsx</code>) to find categories "
    "that are not yet in the reference list."
)
UPLOAD_STEP_HEADING = "Upload Classified Workbook"
UPLOAD_BUTTON = "Upload And Review"
UPLOAD_LOADING = "Uploading And Parsing…"
BACK_TO_CLASSIFY_LABEL = "Back To Categorize"

REVIEW_INTRO_ONE = "Found {n} new category not in the reference list."
REVIEW_INTRO_MANY = "Found {n} new categories not in the reference list."
REVIEW_STEP_HEADING = "Select Categories To Add"
REVIEW_HELP = (
    "Each selected category adds one example ticket and, when needed, a matching routing rule. "
    "&ldquo;Already routable&rdquo; means a rule targets that category today — "
    "the example ticket may still compete with other categories."
)

PREVIEW_STEP_HEADING = "Test On a Ticket Export (Optional)"
PREVIEW_HELP = (
    "Select categories above, then upload a Zendesk export to preview how classification "
    "would change with your selection. Nothing is saved until you confirm."
)
PREVIEW_BUTTON = "Run Preview"
PREVIEW_LOADING = "Running Preview…"
PREVIEW_RESULTS_HEADING = "Preview Results"
PREVIEW_NO_OP_LABEL = (
    "Check Which Categories Have No Impact On This Export (Slower)"
)

SAVE_SELECTED_LABEL = "Save Selected Categories"
CANCEL_LABEL = "Cancel"
DONE_LABEL = "Done"
UNDO_LAST_SAVE = "Undo Last Save"
UNDO_FOOTNOTE = (
    "Restores the reference workbook and routing rules from your most recent save "
    "(disk only — does not undo git history)."
)

GRANULAR_VARIANT_BADGE = "Adds Detail Level"

VERDICT_MESSAGES: dict[str, tuple[str, str]] = {
    "strong_commit": (
        "Looks Good",
        "Saving these categories should improve or maintain classification on this export.",
    ),
    "review": (
        "Review Changes",
        "Some tickets would change — review the list below before saving.",
    ),
    "rules_needed": (
        "Low Impact Expected",
        "Many selected categories may not change any tickets on this export.",
    ),
    "risky": (
        "Caution",
        "Manual review tickets increased — talk to a classifier maintainer before saving.",
    ),
}

DESELECT_NO_OP_BUTTON = "Deselect Categories With No Impact"
SHOW_CHANGE_DETAILS_LABEL = "Show Ticket Change Details"

IMPACT_COLUMN_HEADING = "Impact On Export"
IMPACT_WOULD_CHANGE = "Would Change Tickets"
IMPACT_NO_EFFECT = "No Impact"
IMPACT_NOT_ANALYZED = "Not In Last Preview"
IMPACT_SUMMARY = (
    "On this export: {impactful} would change tickets, {no_op} have no impact "
    "(of {total} in your last preview)."
)
