from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from cs_tickets.classifier_rules import RuleSpec, load_rule_specs
from cs_tickets.schema import TIER_COLUMNS, TIER_FALLBACK_B2C_TBC, TIER_FALLBACK_DEFAULT_TBC
from cs_tickets.taxonomy import AllowList
from cs_tickets.thread_enrich import strip_enrichment

DEFAULT_TBC = TIER_FALLBACK_DEFAULT_TBC
B2C_TBC = TIER_FALLBACK_B2C_TBC

# Sum of matched weighted signals must reach this to accept a scored tuple over fallbacks.
SCORE_THRESHOLD = 5.0
MIN_SCORE_MARGIN = 2.0
HIGH_CONFIDENCE_SCORE = 12.0


@dataclass(frozen=True)
class _RowSignals:
    tags_joined: str
    subject: str
    raw_subject: str
    blob: str
    blob_400: str
    blob_500: str
    blob_600: str
    blob_1200: str
    url: str
    is_reply: bool = False


@dataclass(frozen=True)
class RuleEvidence:
    rule_id: str
    tier: tuple[str, str, str, str, str]
    weight: float
    signal: str


@dataclass(frozen=True)
class ClassificationDecision:
    tier: tuple[str, str, str, str, str]
    score: float
    fallback_used: bool
    candidates: tuple[tuple[tuple[str, str, str, str, str], float], ...]
    evidence: tuple[RuleEvidence, ...]


def _text_lower(value: object) -> str:
    if value is None:
        return ""
    return str(value).lower()


def _tags_list(tags_cell: object) -> list[str]:
    if tags_cell is None:
        return []
    if not isinstance(tags_cell, str):
        tags_cell = str(tags_cell)
    if not tags_cell:
        return []
    try:
        v = json.loads(tags_cell)
        if isinstance(v, list):
            return [str(x).lower() for x in v]
    except json.JSONDecodeError:
        pass
    return [tags_cell.lower()]


def _signals(row: dict[str, Any]) -> _RowSignals:
    tags_s = row.get("_enriched_tags") or row.get("tags")
    tags = _tags_list(tags_s)
    tags_joined = " ".join(tags)
    subject = _text_lower(row.get("subject"))
    raw_subject = _text_lower(row.get("raw_subject"))
    desc = _text_lower(row.get("description"))
    thread = str(row.get("_thread_blob") or "")
    blob = f"{subject} {raw_subject} {desc} {thread}".strip()
    is_reply = bool(row.get("_is_reply")) or (
        subject.startswith("re:")
        or subject.startswith("fw:")
        or " re:" in subject[:30]
    )
    return _RowSignals(
        tags_joined=tags_joined,
        subject=subject,
        raw_subject=raw_subject,
        blob=blob,
        blob_400=blob[:400],
        blob_500=blob[:500],
        blob_600=blob[:600],
        blob_1200=blob[:1200],
        url=_text_lower(row.get("url")),
        is_reply=is_reply,
    )


def _b2b_print_context(sig: _RowSignals) -> bool:
    return (
        "printsupport" in sig.url
        or "printsupport" in sig.tags_joined
        or "print_subs" in sig.tags_joined
        or "print_subscription" in sig.tags_joined
    )


def _word_hit(blob: str, words: tuple[str, ...]) -> bool:
    return any(w in blob for w in words)


def _contains_any(blob: str, needles: tuple[str, ...]) -> bool:
    return any(needle in blob for needle in needles)


def _is_alipayhk_auto_debit_notice(sig: _RowSignals) -> bool:
    """System AlipayHK auto-debit notifications — label before auto-routing as cancel."""
    return "alipayhk" in sig.subject and "auto debit cancellation" in sig.subject


def _is_rosetta_system_email(sig: _RowSignals) -> bool:
    return _word_hit(
        sig.blob_1200,
        ("rosetta system email", "rosetta system e-mail"),
    )


def _is_esp_enterprise_context(sig: _RowSignals) -> bool:
    """Enterprise billing / opportunity IDs (ESP-OPP, ESP-Inv), not bare 'esp' substrings."""
    return _word_hit(
        sig.blob_1200,
        (
            "esp-opp-",
            "esp-inv-",
            "esp-opp",
            "esp-inv",
            "ref#: esp-opp",
            "ref#: esp-inv",
            "subscription no. esp-opp",
            "subscription no. esp-inv",
        ),
    )


def _remap_tier_b2c_to_b2b_sibling(
    tier: tuple[str, str, str, str, str],
    allow: AllowList,
) -> tuple[str, str, str, str, str]:
    if tier[0] != "B2C":
        return tier
    if tier == B2C_TBC and DEFAULT_TBC in allow:
        return DEFAULT_TBC
    sibling = ("B2B", tier[1], tier[2], tier[3], tier[4])
    if sibling in allow:
        return sibling
    if tier[3] == "System Report":
        invoices = (
            "B2B",
            "Service Task",
            "Billing & Admin",
            "Invoices and PO request",
            "N/A",
        )
        if invoices in allow:
            return invoices
    if DEFAULT_TBC in allow:
        return DEFAULT_TBC
    return tier


def _apply_esp_b2b_segment(
    sig: _RowSignals,
    tier: tuple[str, str, str, str, str],
    allow: AllowList,
) -> tuple[str, str, str, str, str]:
    if not _is_esp_enterprise_context(sig):
        return tier
    return _remap_tier_b2c_to_b2b_sibling(tier, allow)


def _is_non_renewal_intent(sig: _RowSignals) -> bool:
    return _word_hit(
        sig.blob_600,
        (
            "non-renewal",
            "non renewal",
            "do not wish to renew",
            "don't want to renew",
            "do not want to renew",
        ),
    ) or _word_hit(
        sig.subject,
        ("non-renewal", "do not wish to renew"),
    ) or "discontinue my subscription" in sig.blob_500 or "discontinue my subscript" in sig.blob_500


def _rule_matches(rule: RuleSpec, sig: _RowSignals) -> bool:
    if rule.requires_b2b_print_context and not _b2b_print_context(sig):
        return False
    if rule.id.startswith("sales.renewal") and (
        _is_non_renewal_intent(sig) or _is_rosetta_system_email(sig)
    ):
        return False
    tags = set(sig.tags_joined.split())
    if rule.all_tags and not all(tag in tags for tag in rule.all_tags):
        return False
    if rule.any_tags and not any(tag in tags for tag in rule.any_tags):
        return False
    if rule.any_subject and not _contains_any(sig.subject, rule.any_subject):
        return False
    if rule.any_blob and not _contains_any(sig.blob_1200, rule.any_blob):
        return False
    if rule.exclude_blob and _contains_any(sig.blob_1200, rule.exclude_blob):
        return False
    if rule.any_url and not _contains_any(sig.url, rule.any_url):
        return False
    return True


def tbc_reason(decision: ClassificationDecision) -> str:
    """Bucket fallback TBC cause; mirrors ``_accepted_score`` logic."""
    if not decision.fallback_used:
        return "not_tbc"
    if not decision.candidates:
        if decision.evidence:
            return "allowlist_filtered"
        return "zero_candidate"
    best_s = decision.candidates[0][1]
    if best_s < SCORE_THRESHOLD:
        return "below_threshold"
    if (
        len(decision.candidates) >= 2
        and best_s - decision.candidates[1][1] < MIN_SCORE_MARGIN
    ):
        return "lost_margin"
    return "other"


def _score_tiers(
    sig: _RowSignals,
    allow: AllowList,
    *,
    rule_specs: tuple[RuleSpec, ...] | None = None,
) -> tuple[dict[tuple[str, str, str, str, str], float], list[RuleEvidence]]:
    scores: dict[tuple[str, str, str, str, str], float] = {}
    evidence: list[RuleEvidence] = []

    def add(
        t: tuple[str, str, str, str, str],
        w: float,
        *,
        rule_id: str | None = None,
        signal: str = "",
    ) -> None:
        if w <= 0.0 or t not in allow:
            return
        scores[t] = scores.get(t, 0.0) + w
        evidence.append(
            RuleEvidence(
                rule_id=rule_id or f"legacy:{'|'.join(t)}",
                tier=t,
                weight=w,
                signal=signal,
            )
        )

    cancel_tuple = ("B2C", "Complaint", "Refund", "Cancellation Request", "N/A")

    # --- Non-renewal / discontinue (before renewal rules; beats renewal-inquiry ties) ---
    if _is_non_renewal_intent(sig):
        add(cancel_tuple, 14.0, rule_id="computed:non_renewal_cancel.b2c", signal="computed")

    specs = rule_specs if rule_specs is not None else load_rule_specs()
    for rule in specs:
        if _rule_matches(rule, sig):
            add(rule.tier, rule.weight, rule_id=rule.id, signal="data_rule")

    # --- Subscriber chat on account portal (zopim, not subscribe.scmp empty trigger) ---
    tok = set(sig.tags_joined.split())
    is_account_chat = (
        "zopim_chat" in tok
        and "conversation with" in sig.subject
        and "account.scmp.com" in sig.blob_1200
    )
    if is_account_chat:
        if "subscription_-_refund" in tok or "subscription_-_cancellation_refund" in tok:
            add(
                ("B2C", "Complaint", "Refund", "Cancellation Request", "N/A"),
                12.0,
                rule_id="computed:chat_account_refund.b2c",
                signal="computed",
            )
        elif "subscription_-_save_the_stop__churn_recovery_" in tok:
            add(
                ("B2C", "Service Task", "General Support", "Retention Offer", "N/A"),
                11.0,
                rule_id="computed:chat_account_churn.b2c",
                signal="computed",
            )
        elif _contains_any(
            sig.blob_1200,
            ("upgrade=true", "manage/subscription?upgrade", "?upgrade"),
        ):
            pass
        elif (
            "existing_subscriber" in tok
            or "new_subscriber" in tok
            or "annual_term" in tok
            or "monthly_term" in tok
            or "bi-annual_term" in tok
            or "subscription_-_other" in tok
            or "account_-_method" in tok
        ):
            add(
                ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"),
                10.0,
                rule_id="computed:chat_account_subscriber.b2c",
                signal="computed",
            )

    # --- Email reply threads with renewal / PO cues in subject ---
    if sig.is_reply and _word_hit(
        sig.subject,
        (
            "scmp renewal",
            "subscription renewal",
            "renewal, exp",
            "renewal 26/",
            "renewal 27/",
        ),
    ) and not _is_non_renewal_intent(sig):
        add(
            ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"),
            10.0,
            rule_id="computed:reply_renewal_subject.b2c",
            signal="computed",
        )

    # --- Reply inherits parent subscriber tags (thread enrichment) ---
    if sig.is_reply:
        reply_tok = set(sig.tags_joined.split())
        if (
            "existing_subscriber" in reply_tok
            or "new_subscriber" in reply_tok
            or "annual_term" in reply_tok
            or "monthly_term" in reply_tok
            or "bi-annual_term" in reply_tok
            or "subscription_-_other" in reply_tok
            or "account_-_method" in reply_tok
            or "subscription_-_renew" in reply_tok
            or "account_renewal" in reply_tok
        ) and not _is_non_renewal_intent(sig):
            add(
                ("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"),
                10.0,
                rule_id="computed:reply_inherit_parent_tags.b2c",
                signal="computed",
            )

    # --- Press / junk ---
    if (
        "press release" in sig.subject
        or "press release" in sig.raw_subject
        or "[press release]" in sig.subject
    ):
        add(("B2C", "Junk", "Junk", "PR / External Sales / Editorial Noise", "N/A"), 15.0)
        add(("B2B", "Junk", "Junk", "PR / External Sales / Editorial Noise", "N/A"), 13.0)
    if "junk" in sig.tags_joined:
        add(("B2C", "Junk", "Junk", "Junk", "N/A"), 13.0)

    # --- Refund / cancel (B2C default; stronger B2B when print context) ---
    has_refund = any(
        x in sig.tags_joined for x in ("refund", "subscription_-_refund")
    ) or "refund" in sig.blob_400
    if has_refund:
        if "cancel" in sig.blob_500:
            if _b2b_print_context(sig):
                add(("B2B", "Complaint", "Refund", "Cancellation Request", "N/A"), 24.0)
            add(cancel_tuple, 22.0, rule_id="computed:refund_cancel.b2c", signal="computed")
        else:
            add(("B2C", "Complaint", "Refund", "Refund Request", "N/A"), 12.0)

    # --- Cancel language without refund tag (skip AlipayHK system notices) ---
    if (
        not has_refund
        and not _is_alipayhk_auto_debit_notice(sig)
        and not _is_non_renewal_intent(sig)
        and _word_hit(
            sig.blob_600,
            (
                "cancel my subscription",
                "cancel subscription",
                "please cancel",
                "want to cancel",
                "termination inquiry",
                "terminate the subscription",
                "cancel our services",
            ),
        )
    ):
        add(cancel_tuple, 12.0, rule_id="computed:cancel_language.b2c", signal="computed")

    # --- Invoices / PO ---
    if (
        "invoice" in sig.blob_600
        or "invoice" in sig.tags_joined
        or "po_number" in sig.tags_joined
    ):
        add(("B2C", "Service Task", "Billing & Admin", "Invoices and PO request", "N/A"), 12.0)
        add(("B2B", "Service Task", "Billing & Admin", "Invoices and PO request", "N/A"), 10.0)
        add(("B2B", "Service Task", "Account Management", "Invoices and PO request", "N/A"), 9.0)

    # --- Print logistics (tags; B2B + B2C tuples in allowlist) ---
    _logistics_tags = ("print_subs", "print_subscription", "suspension_-_print_suspension_request")
    if any(k in sig.tags_joined for k in _logistics_tags):
        add(
            (
                "B2B",
                "Service Task",
                "Logistics",
                "Print Subs - Suspension and Resume confirmation",
                "N/A",
            ),
            16.0,
        )
        add(
            (
                "B2C",
                "Service Task",
                "Logistics",
                "Print Subs - Suspension and Resume confirmation",
                "N/A",
            ),
            15.0,
        )

    # --- B2B / printsupport: extra granular paths from allowlist (keyword scoring) ---
    if _b2b_print_context(sig):
        b = sig.blob_1200
        tj = sig.tags_joined

        # Renewal / subscription (Zendesk tags + subject/body — drives most B2B TBC volume)
        renew_tags = (
            "subscription_-_renew",
            "account_renewal",
            "annual_term",
            "monthly_term",
            "subscription_-_new",
        )
        has_renew_tag = any(ng in tj for ng in renew_tags)
        if "existing_subscriber" in tj and (
            "renewal" in sig.blob_500
            or " renew" in sig.blob_400
            or "annual_term" in tj
            or "monthly_term" in tj
        ):
            has_renew_tag = True
        if "digital" in tj and "renewal" in sig.blob_500:
            has_renew_tag = True
        renew_blob = _word_hit(
            sig.blob_600,
            (
                "renewal",
                " renew ",
                "subscription period",
                "scmp renewal",
                "renew your",
                "renewal and",
                "auto debit",
            ),
        )
        renew_subject = _word_hit(
            sig.subject,
            (
                "renewal",
                "renew ",
                "alipayhk",
                "reminder of your",
                "scmp order",
                "delivery service",
                "bundle transactions",
                "paywall",
                "subscription renewal",
                "your scmp",
                "resumption",
            ),
        )
        if has_renew_tag or renew_blob or renew_subject:
            add(("B2B", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"), 13.0)
            add(("B2C", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"), 10.0)

        if "existing_subscriber" in tj and "digital" in tj:
            add(("B2B", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"), 8.0)

        # Common Zendesk tag combos on print-support queue (no keyword in subject/body)
        tok = set(tj.split())
        stack = 0.0
        if "digital" in tok:
            stack += 3.0
        if "existing_subscriber" in tok:
            stack += 3.0
        if "sfpayment" in tok:
            stack += 2.5
        if "customer_-_misc" in tok:
            stack += 2.0
        if "other_departments" in tok:
            stack += 1.5
        if "annual_term" in tok or "monthly_term" in tok:
            stack += 2.0
        if "subscription_-_renew" in tok or "account_renewal" in tok:
            stack += 4.0
        if stack >= SCORE_THRESHOLD:
            add(("B2B", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"), stack)

        if _word_hit(b, ("archive", "archival", "reprint", "editorial request", "pull story")):
            add(
                ("B2B", "Service Task", "Editorial Feedback", "Editorial / Archive Request", "N/A"),
                9.0,
            )
        if _word_hit(b, ("content feedback", "feedback on article", "article feedback", "story feedback")):
            add(("B2B", "Service Task", "Editorial Feedback", "Content Feedback", "N/A"), 9.0)

        if _word_hit(
            b,
            ("gift subscription", "gift purchase", "corporate gift", "bulk gift", "gift order"),
        ):
            add(("B2B", "Service Task", "Sales Leads", "Gift Purchase Inquiry", "N/A"), 9.0)

        if _word_hit(
            b,
            ("pricing", "quotation", "quote request", "rate card", "cost per copy", "price list"),
        ):
            add(
                (
                    "B2B",
                    "Service Task",
                    "Sales Leads",
                    "Inquiry for pricing",
                    "Tech: General Technical Glitch",
                ),
                9.0,
            )

        if _word_hit(b, ("renewal", "renew ", "rate change", "subscription rate", "renewal quote")):
            add(("B2B", "Service Task", "Sales Leads", "Rate or Renewal Inquiry", "N/A"), 9.0)

        if "upgrade" in b or "upgrade inquiry" in b or "plan upgrade" in b:
            add(("B2B", "Service Task", "Sales Leads", "Upgrade Inquiry", "N/A"), 9.0)

        if _word_hit(
            b,
            (
                "ui/ux",
                "user interface",
                "confusing layout",
                "hard to find",
                "usability",
                "navigation issue",
                "ux friction",
            ),
        ):
            add(("B2B", "Service Task", "General Support", "UI/UX Friction", "N/A"), 9.0)

        if _word_hit(b, ("user error", "wrong file", "sent wrong", "correction request")):
            add(("B2B", "Service Task", "Account Management", "User Error / Correction", "N/A"), 8.0)

    return scores, evidence


def _tier4_is_tbc(t: tuple[str, str, str, str, str]) -> bool:
    return "tbc" in (t[3] or "").lower()


def _pick_best(
    scores: dict[tuple[str, str, str, str, str], float],
) -> tuple[tuple[str, str, str, str, str] | None, float]:
    if not scores:
        return None, 0.0

    def sort_key(t: tuple[str, str, str, str, str]) -> tuple[float, int, str]:
        s = scores[t]
        non_tbc = 0 if _tier4_is_tbc(t) else 1
        return (s, non_tbc, t[3] or "")

    best = max(scores, key=sort_key)
    return best, scores[best]


def _accepted_score(
    candidates: tuple[tuple[tuple[str, str, str, str, str], float], ...],
) -> bool:
    if not candidates:
        return False
    best_s = candidates[0][1]
    if best_s < SCORE_THRESHOLD:
        return False
    if best_s >= HIGH_CONFIDENCE_SCORE:
        return True
    if len(candidates) == 1:
        return True
    return best_s - candidates[1][1] >= MIN_SCORE_MARGIN


def classify_row_with_explanation(
    row: dict[str, Any],
    allow: AllowList,
    *,
    rule_specs: tuple[RuleSpec, ...] | None = None,
) -> ClassificationDecision:
    """Weighted tier assignment with rule evidence and candidate scores."""
    sig = _signals(row)
    scores, evidence = _score_tiers(sig, allow, rule_specs=rule_specs)
    best, best_s = _pick_best(scores)
    candidates = tuple(
        sorted(scores.items(), key=lambda item: item[1], reverse=True)
    )
    if best is not None and _accepted_score(candidates):
        tier = _apply_esp_b2b_segment(sig, best, allow)
        return ClassificationDecision(
            tier=tier,
            score=best_s,
            fallback_used=False,
            candidates=candidates,
            evidence=tuple(evidence),
        )

    b2b_hint = _b2b_print_context(sig)
    if b2b_hint and DEFAULT_TBC in allow:
        tier = DEFAULT_TBC
    elif B2C_TBC in allow:
        tier = B2C_TBC
    elif DEFAULT_TBC in allow:
        tier = DEFAULT_TBC
    else:
        tier = next(iter(sorted(allow.tuples)))
    tier = _apply_esp_b2b_segment(sig, tier, allow)
    return ClassificationDecision(
        tier=tier,
        score=best_s,
        fallback_used=True,
        candidates=candidates,
        evidence=tuple(evidence),
    )


def classify_row(row: dict[str, Any], allow: AllowList) -> tuple[str, str, str, str, str]:
    """Weighted multi-signal tier assignment; fallbacks preserve B2B/B2C TBC behavior."""
    return classify_row_with_explanation(row, allow).tier


def _is_tbc_decision(decision: ClassificationDecision) -> bool:
    """Same as allowlist_compare._is_tbc and tbc_trends._is_tbc."""
    return decision.fallback_used or "tbc" in decision.tier[3].lower()


def portal_reason_bucket(
    decision: ClassificationDecision,
    *,
    output_row: dict[str, Any] | None = None,
) -> str:
    """Map a classification decision → display bucket code for portal / audit alignment."""
    from cs_tickets.portal_stats import is_manual_review_row

    if _is_tbc_decision(decision):
        reason = tbc_reason(decision)
        return "other" if reason == "not_tbc" else reason
    if output_row is not None and is_manual_review_row(output_row):
        return "other"
    return "not_tbc"


def attach_tiers_with_meta(
    row: dict[str, Any], allow: AllowList
) -> tuple[dict[str, Any], str | None, str]:
    """Return master row, optional warning, and portal TBC reason bucket."""
    decision = classify_row_with_explanation(row, allow)
    tier = decision.tier
    warn: str | None = None
    if tier not in allow:
        tier = DEFAULT_TBC if DEFAULT_TBC in allow else next(iter(sorted(allow.tuples)))
        warn = "tier_coerced_not_in_allowlist"
    out = dict(row)
    for col, val in zip(TIER_COLUMNS, tier, strict=True):
        out[col] = val
    final = tuple(out[c] for c in TIER_COLUMNS)
    if final not in allow:
        warn = warn or "tier_still_invalid"
    out = strip_enrichment(out)
    reason = portal_reason_bucket(decision, output_row=out)
    return out, warn, reason


def attach_tiers(row: dict[str, Any], allow: AllowList) -> tuple[dict[str, Any], str | None]:
    """Return full master row dict with tier columns; optional warning if coerced."""
    out, warn, _ = attach_tiers_with_meta(row, allow)
    return out, warn
