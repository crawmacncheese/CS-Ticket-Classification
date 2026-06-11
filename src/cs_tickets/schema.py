# Column contract: sheet SCMP_Tickets_Master_Categorized in doc/CS_ticket_new_categorizations.xlsx
MASTER_COLUMNS: tuple[str, ...] = (
    "url",
    "id",
    "external_id",
    "created_at",
    "updated_at",
    "generated_timestamp",
    "type",
    "subject",
    "raw_subject",
    "description",
    "priority",
    "status",
    "follower_ids",
    "email_cc_ids",
    "forum_topic_id",
    "problem_id",
    "has_incidents",
    "is_public",
    "due_at",
    "tags",
    "Tier1_Segment",
    "Tier2_Stream",
    "Tier3_Cat",
    "Tier4_Type",
    "Granular_Tech_UI_Type",
)
BASE_COLUMNS: tuple[str, ...] = MASTER_COLUMNS[:20]
TIER_COLUMNS: tuple[str, ...] = MASTER_COLUMNS[20:]

# Classifier fallbacks: always unioned in `load_allowlist` (not sourced from Taxonomy.csv).
TIER_FALLBACK_DEFAULT_TBC: tuple[str, str, str, str, str] = (
    "B2B",
    "Service Task",
    "General Support",
    "TBC (Manual Review)",
    "N/A",
)
TIER_FALLBACK_B2C_TBC: tuple[str, str, str, str, str] = (
    "B2C",
    "Service Task",
    "General Support",
    "TBC (Manual Review)",
    "N/A",
)
PIPELINE_FALLBACK_TIER_TUPLES: frozenset[tuple[str, str, str, str, str]] = frozenset(
    {TIER_FALLBACK_DEFAULT_TBC, TIER_FALLBACK_B2C_TBC}
)
