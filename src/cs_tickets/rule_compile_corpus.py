"""Few-shots, precedence corpus, and golden compile fixtures for ``rule_compile``.

Source: client CS Christine Gemini export + ``docs/plans/2026-07-03-gemini-conversation-patterns.md``.
Tier paths are workbook 5-tuples; ``rule_compile`` must validate every tier against ``AllowList``.

Not imported by ``classify.py`` or the ``/run`` hot path — compile/authoring only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- Precedence (client master prompt V18/V34) --------------------------------

PRECEDENCE_CORPUS = """\
Evaluate shield rules BEFORE financial/growth rules. When the user says CRITICAL, always,
even if refund, or names a shield rule, assign override=true and the matching weight band.

1. No Content / live-chat auto-trigger — subject "Conversation with" + URL-only or subscribe
   landing body → General Support > No Content - Live chat auto-trigger. NOT Sales Lead.
2. Stefan Rule — moderation friction, deleted comments, biased moderators → Account Management
   > Comments being block. Beats refund/cancel keywords in the same ticket.
3. External junk / vendor / HR — PR pitches, job applications → Junk > PR / External Sales /
   Editorial Noise. Never Upgrade or Sales Leads.
4. Financial / growth / B2B — normal weighted rules (renewal, billing, bugs, B2B corp names).
"""

SHIELD_WEIGHT_MIN: dict[str, float] = {
    "live_chat": 20.0,
    "stefan": 18.0,
    "junk": 16.0,
    "default_min": 8.0,
    "default_max": 14.0,
}

# --- Taxonomy disambiguation (Gem 4-tier → workbook 5-tuple) --------------------

TAXONOMY_DISAMBIGUATION: tuple[tuple[str, str], ...] = (
    (
        "Service Task > Need help for Cancellation",
        "Complaint > Refund > Cancellation Request",
    ),
    (
        "Account Management > Comments blocked",
        "Account Management > Comments being block",
    ),
    (
        "Billing & Admin > System Report",
        "Billing & Admin > System Report",
    ),
)

# --- Few-shot pairs for system prompt (user utterance → compiler intent) --------

FEW_SHOT_PAIRS: tuple[dict[str, str], ...] = (
    {
        "user": (
            'Update: Map "how can i renew my scmp" or "renewal reminder" to '
            "Sales Leads > Rate or Renewal Inquiry."
        ),
        "intent": (
            "any_blob renewal phrases → B2C Service Task Sales Leads "
            "Rate or Renewal Inquiry; weight ~10; override false"
        ),
    },
    {
        "user": 'Update: Map "Stripe payment completed" to Billing & Admin > System Report.',
        "intent": (
            "any_blob stripe payment completed → B2C Billing & Admin System Report; "
            "weight ~10; override false"
        ),
    },
    {
        "user": (
            "If it contains Rosetta System Email, that is system email — "
            "NOT cancellation request."
        ),
        "intent": (
            "any_blob rosetta system email → System Report; exclude_blob cancel/refund "
            "keywords; weight ~14; override false"
        ),
    },
    {
        "user": "CRITICAL: Do NOT mark Conversation with + URL-only as Sales Lead.",
        "intent": (
            "any_subject conversation with + subscribe URL blob → No Content live-chat "
            "auto-trigger; override true; weight >= 20; exclude_blob upgrade/sales signals"
        ),
    },
    {
        "user": (
            "Stefan Rule: moderation / deleted comments → Account Management "
            "even if refund mentioned."
        ),
        "intent": (
            "display_name Stefan Rule; any_blob moderation/deleted comment phrases → "
            "Account Management Comments being block; override true; weight >= 18"
        ),
    },
)

# --- Input normalizer: paraphrase hints (regex or substring → canonical tag) ----

INPUT_NORMALIZER_HINTS: tuple[tuple[str, str], ...] = (
    ('update: map "', "update_map"),
    ("map ", "update_map"),
    ("always category", "override_intent"),
    ("every time", "override_intent"),
    ("critical:", "shield_critical"),
    ("do not mark", "exclude_intent"),
    ("not cancellation", "exclude_intent"),
    ("stefan rule", "named_stefan"),
    ("replace rule ", "replace_flow"),
)

# --- TBC → compile chat prefill template ----------------------------------------

TBC_COMPILE_PREFILL_TEMPLATE = """\
Ticket #{ticket_id} — "{subject_snippet}"

"{quote_snippet}"

The classifier left this for manual review: {why_tbc}. {classifier_note}
{target_line}

Update: Map tickets with this pattern to [your target category].
"""

# --- Golden compile fixtures (mocked LLM tests; partial expected RuleSpec) ----

TierTuple = tuple[str, str, str, str, str]

_B2C = "B2C"
_SERVICE = "Service Task"
_BILLING = "Billing & Admin"
_SYSTEM_REPORT = "System Report"
_SALES = "Sales Leads"
_RENEWAL = "Rate or Renewal Inquiry"
_GENERAL = "General Support"
_LIVE_CHAT = "No Content - Live chat auto-trigger"
_ACCOUNT = "Account Management"
_COMMENTS_BLOCK = "Comments being block"
_JUNK = "Junk"
_JUNK_NOISE = "PR / External Sales / Editorial Noise"
_NA = "N/A"


@dataclass(frozen=True)
class GoldenCompileFixture:
    """One client pattern → expected compile output shape (validator asserts subset)."""

    id: str
    user_messages: tuple[str, ...]
    expected: dict[str, Any]
    notes: str = ""
    paraphrases_only: bool = False


def _tier(*parts: str) -> TierTuple:
    return (*parts, _NA) if len(parts) == 4 else (parts[0], parts[1], parts[2], parts[3], parts[4])


GOLDEN_COMPILE_FIXTURES: tuple[GoldenCompileFixture, ...] = (
    GoldenCompileFixture(
        id="rosetta_system_email",
        user_messages=(
            "If it contains Rosetta System Email, that is system email — NOT cancellation request.",
            "#169856 is NOT cancellation — Rosetta footer",
            "Rosetta system email should be system report not cancel",
        ),
        expected={
            "tier": _tier(_B2C, _SERVICE, _BILLING, _SYSTEM_REPORT),
            "any_blob": ("rosetta system email",),
            "exclude_blob": (),  # compiler may add cancel/refund excludes; test allows superset
            "override": False,
            "weight_min": 10.0,
        },
        notes="Aligns with billing.system_report.rosetta_renewal.b2c in classifier_rules.json",
    ),
    GoldenCompileFixture(
        id="stripe_payment_completed",
        user_messages=(
            'Update: Map "Stripe payment completed" to Billing & Admin > System Report.',
            "Stripe payment completed notifications are system reports",
        ),
        expected={
            "tier": _tier(_B2C, _SERVICE, _BILLING, _SYSTEM_REPORT),
            "any_blob": ("stripe payment completed",),
            "override": False,
        },
        notes="Aligns with billing.system_report.payment.b2c",
    ),
    GoldenCompileFixture(
        id="payment_advice_note",
        user_messages=(
            'Update: Map "payment advice note" to Billing & Admin > System Report.',
        ),
        expected={
            "tier": _tier(_B2C, _SERVICE, _BILLING, _SYSTEM_REPORT),
            "any_blob": ("payment advice note",),
            "override": False,
        },
    ),
    GoldenCompileFixture(
        id="live_chat_url_only_shield",
        user_messages=(
            "CRITICAL: Do NOT mark Conversation with + URL-only as Sales Lead.",
            "Conversation with subject and only subscribe URL in body is live chat auto-trigger",
        ),
        expected={
            "tier": _tier(_B2C, _SERVICE, _GENERAL, _LIVE_CHAT),
            "any_subject": ("conversation with",),
            "override": True,
            "weight_min": SHIELD_WEIGHT_MIN["live_chat"],
        },
        notes="Open Q: URL-only body heuristic — validate on PDF fixtures before shipping",
    ),
    GoldenCompileFixture(
        id="stefan_rule_moderation",
        user_messages=(
            "Stefan Rule: moderation / deleted comments → Account Management even if refund mentioned.",
            "deleted comment moderation issue should be account management not refund",
        ),
        expected={
            "display_name": "Stefan Rule",
            "tier": _tier(_B2C, _SERVICE, _ACCOUNT, _COMMENTS_BLOCK),
            "any_blob": (),  # compiler picks phrases; test checks override + tier
            "override": True,
            "weight_min": SHIELD_WEIGHT_MIN["stefan"],
        },
        notes="Workbook tier is 'Comments being block' (Taxonomy.csv)",
    ),
    GoldenCompileFixture(
        id="renewal_inquiry",
        user_messages=(
            'Update: Map "how can i renew my scmp" or "renewal reminder" to '
            "Sales Leads > Rate or Renewal Inquiry.",
            "how can i renew my scmp → renewal inquiry",
        ),
        expected={
            "tier": _tier(_B2C, _SERVICE, _SALES, _RENEWAL),
            "any_blob": ("how can i renew my scmp", "renewal reminder"),
            "override": False,
        },
    ),
    GoldenCompileFixture(
        id="junk_pr_pitch",
        user_messages=(
            "PR pitch emails are junk not sales leads",
            "External vendor HR job application → Junk",
        ),
        expected={
            "tier": _tier(_B2C, _JUNK, _JUNK, _JUNK_NOISE),
            "override": True,
            "weight_min": SHIELD_WEIGHT_MIN["junk"],
        },
    ),
    GoldenCompileFixture(
        id="privaterelay_sender_signal",
        user_messages=(
            "Tickets from privaterelay.appleid.com are often refund/cancel context",
            "If sender is privaterelay.appleid.com treat as refund cancel signal",
        ),
        expected={
            "any_requester_domain": ("privaterelay.appleid.com",),
            "override": False,
        },
        notes="Tier left to maintainer / exemplar — sender signal only",
    ),
    GoldenCompileFixture(
        id="tbc_prefill_from_ticket",
        user_messages=(
            'When tickets look like #167391 ("paid but can\'t access article"), '
            "they should be Access Loop or App Bug because didn't trigger access rule.",
        ),
        expected={
            "any_blob": (),  # derived from exemplar when run_id+ticket_id present
            "override": False,
        },
        notes="Requires exemplar ticket in compile request; tier must resolve via allow-list",
        paraphrases_only=True,
    ),
)


@dataclass
class CompileCorpus:
    """Bundle injected into ``rule_compile`` system prompt assembly."""

    precedence: str = PRECEDENCE_CORPUS
    few_shots: tuple[dict[str, str], ...] = field(default_factory=lambda: FEW_SHOT_PAIRS)
    disambiguation: tuple[tuple[str, str], ...] = field(
        default_factory=lambda: TAXONOMY_DISAMBIGUATION
    )
    shield_weights: dict[str, float] = field(default_factory=lambda: dict(SHIELD_WEIGHT_MIN))


DEFAULT_CORPUS = CompileCorpus()


def format_few_shots_for_prompt(pairs: tuple[dict[str, str], ...] | None = None) -> str:
    """Render few-shot block for the compile system prompt."""
    lines: list[str] = ["## Few-shot compile examples", ""]
    for pair in pairs or FEW_SHOT_PAIRS:
        lines.append(f"User: {pair['user']}")
        lines.append(f"Compiler intent: {pair['intent']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def format_disambiguation_for_prompt(
    pairs: tuple[tuple[str, str], ...] | None = None,
) -> str:
    lines: list[str] = ["## Taxonomy disambiguation (workbook wins)", ""]
    for gem_path, workbook_path in pairs or TAXONOMY_DISAMBIGUATION:
        lines.append(f"- Gem/session: {gem_path}")
        lines.append(f"  Workbook: {workbook_path}")
    return "\n".join(lines)
