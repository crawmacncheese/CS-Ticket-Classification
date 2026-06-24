from __future__ import annotations



from dataclasses import dataclass

from pathlib import Path



from cs_tickets.classifier_rules import RuleSpec, load_rule_specs

from cs_tickets.classify import classify_row_with_explanation, tbc_reason

from cs_tickets.thread_enrich import (
    build_ticket_index,
    flatten_for_classify,
    thread_enrichment_enabled,
)

from cs_tickets.pipeline import _iter_ticket_dicts

from cs_tickets.satisfaction import has_bad_satisfaction_rating

from cs_tickets.taxonomy import AllowList





@dataclass(frozen=True)

class AllowlistCompareResult:

    total: int

    tbc_old: int

    tbc_new: int

    changed_rows: list[dict]

    zero_candidate_old: int

    zero_candidate_new: int

    allowlist_old_size: int = 0

    allowlist_new_size: int = 0

    tuples_merged: int = 0

    tbc_b2b_old: int = 0

    tbc_b2b_new: int = 0

    tbc_b2c_old: int = 0

    tbc_b2c_new: int = 0

    margin_loss_old: int = 0

    margin_loss_new: int = 0

    below_threshold_old: int = 0

    below_threshold_new: int = 0

    allowlist_filtered_old: int = 0

    allowlist_filtered_new: int = 0

    other_old: int = 0

    other_new: int = 0

    rules_targeting_selected_old: int = 0

    rules_targeting_selected_new: int = 0

    bad_satisfaction_only: bool = False





def _is_tbc(decision) -> bool:

    return decision.fallback_used or "tbc" in decision.tier[3].lower()





def enrich_changed_row(old_dec, new_dec) -> dict:

    old_tbc = _is_tbc(old_dec)

    new_tbc = _is_tbc(new_dec)

    old_zero = not old_dec.candidates

    new_zero = not new_dec.candidates

    outcome_type: str

    gap_fix_mechanism: str | None = None

    if old_tbc and not new_tbc:

        outcome_type = "gap_fix"

        gap_fix_mechanism = "allowlist_gap" if old_zero else "scoring_recovery"

    elif not old_tbc and new_tbc:

        outcome_type = "regression"

    else:

        outcome_type = "reroute"

    seg = (old_dec.tier[0] or new_dec.tier[0] or "").strip().upper()

    segment = seg if seg in ("B2B", "B2C") else None

    return {

        "outcome_type": outcome_type,

        "gap_fix_mechanism": gap_fix_mechanism,

        "old_tbc": old_tbc,

        "new_tbc": new_tbc,

        "old_tbc_reason": tbc_reason(old_dec) if old_tbc else None,

        "new_tbc_reason": tbc_reason(new_dec) if new_tbc else None,

        "old_zero_candidate": old_zero,

        "new_zero_candidate": new_zero,

        "segment": segment,

    }





def _tbc_segment(decision) -> str | None:

    if not _is_tbc(decision):

        return None

    seg = (decision.tier[0] or "").strip().upper()

    if seg == "B2B":

        return "b2b"

    if seg == "B2C":

        return "b2c"

    return None





def _count_tbc_bucket(decision, bucket: str) -> bool:

    return _is_tbc(decision) and tbc_reason(decision) == bucket





def _compare_row(

    row: dict,

    allow_old: AllowList,

    allow_new: AllowList,

    *,

    rule_specs_old: tuple[RuleSpec, ...] | None,

    rule_specs_new: tuple[RuleSpec, ...] | None,

    total: int,

    tbc_old: int,

    tbc_new: int,

    tbc_b2b_old: int,

    tbc_b2b_new: int,

    tbc_b2c_old: int,

    tbc_b2c_new: int,

    zero_candidate_old: int,

    zero_candidate_new: int,

    margin_loss_old: int,

    margin_loss_new: int,

    below_threshold_old: int,

    below_threshold_new: int,

    allowlist_filtered_old: int,

    allowlist_filtered_new: int,

    other_old: int,

    other_new: int,

    changed_rows: list[dict],

    enrich_changed_rows: bool = False,

) -> tuple[int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int, int]:

    old_dec = classify_row_with_explanation(row, allow_old, rule_specs=rule_specs_old)

    new_dec = classify_row_with_explanation(row, allow_new, rule_specs=rule_specs_new)

    total += 1

    if _is_tbc(old_dec):

        tbc_old += 1

        seg = _tbc_segment(old_dec)

        if seg == "b2b":

            tbc_b2b_old += 1

        elif seg == "b2c":

            tbc_b2c_old += 1

        if _count_tbc_bucket(old_dec, "zero_candidate"):

            zero_candidate_old += 1

        if _count_tbc_bucket(old_dec, "allowlist_filtered"):

            allowlist_filtered_old += 1

        if _count_tbc_bucket(old_dec, "below_threshold"):

            below_threshold_old += 1

        if _count_tbc_bucket(old_dec, "lost_margin"):

            margin_loss_old += 1

        if _count_tbc_bucket(old_dec, "other"):

            other_old += 1

    if _is_tbc(new_dec):

        tbc_new += 1

        seg = _tbc_segment(new_dec)

        if seg == "b2b":

            tbc_b2b_new += 1

        elif seg == "b2c":

            tbc_b2c_new += 1

        if _count_tbc_bucket(new_dec, "zero_candidate"):

            zero_candidate_new += 1

        if _count_tbc_bucket(new_dec, "allowlist_filtered"):

            allowlist_filtered_new += 1

        if _count_tbc_bucket(new_dec, "below_threshold"):

            below_threshold_new += 1

        if _count_tbc_bucket(new_dec, "lost_margin"):

            margin_loss_new += 1

        if _count_tbc_bucket(new_dec, "other"):

            other_new += 1

    if old_dec.tier != new_dec.tier:

        row_data: dict = {

            "id": str(row.get("id") or ""),

            "subject": row.get("subject"),

            "description": row.get("description"),

            "tags": row.get("tags"),

            "old_tier4": old_dec.tier[3],

            "new_tier4": new_dec.tier[3],

            "old_tuple": old_dec.tier,

            "new_tuple": new_dec.tier,

        }

        if enrich_changed_rows:

            row_data.update(enrich_changed_row(old_dec, new_dec))

        changed_rows.append(row_data)

    return (

        total,

        tbc_old,

        tbc_new,

        tbc_b2b_old,

        tbc_b2b_new,

        tbc_b2c_old,

        tbc_b2c_new,

        zero_candidate_old,

        zero_candidate_new,

        margin_loss_old,

        margin_loss_new,

        below_threshold_old,

        below_threshold_new,

        allowlist_filtered_old,

        allowlist_filtered_new,

        other_old,

        other_new,

    )





def _rules_targeting_selected(

    selected: frozenset[tuple[str, str, str, str, str]] | None,

    rule_specs: tuple[RuleSpec, ...] | None,

) -> int:

    if not selected or rule_specs is None:

        return 0

    return sum(1 for rule in rule_specs if rule.tier in selected)





def compare_allowlists_on_ndjson(

    ndjson_path: Path,

    allow_old: AllowList,

    allow_new: AllowList,

    *,

    limit: int | None = None,

    allowlist_old_size: int = 0,

    allowlist_new_size: int = 0,

    tuples_merged: int = 0,

    rule_specs_old: tuple[RuleSpec, ...] | None = None,

    rule_specs_new: tuple[RuleSpec, ...] | None = None,

    selected_tuples: frozenset[tuple[str, str, str, str, str]] | None = None,

    enrich_changed_rows: bool = False,

    bad_satisfaction_only: bool = False,

) -> AllowlistCompareResult:

    default_rules = load_rule_specs()

    specs_old = rule_specs_old if rule_specs_old is not None else default_rules

    specs_new = rule_specs_new if rule_specs_new is not None else specs_old



    total = 0

    tbc_old = 0

    tbc_new = 0

    tbc_b2b_old = 0

    tbc_b2b_new = 0

    tbc_b2c_old = 0

    tbc_b2c_new = 0

    zero_candidate_old = 0

    zero_candidate_new = 0

    margin_loss_old = 0

    margin_loss_new = 0

    below_threshold_old = 0

    below_threshold_new = 0

    allowlist_filtered_old = 0

    allowlist_filtered_new = 0

    other_old = 0

    other_new = 0

    changed_rows: list[dict] = []

    thread_index = (
        build_ticket_index(_iter_ticket_dicts(ndjson_path))
        if thread_enrichment_enabled()
        else {}
    )

    for ticket in _iter_ticket_dicts(ndjson_path):

        if bad_satisfaction_only and not has_bad_satisfaction_rating(ticket):

            continue

        if limit is not None and total >= limit:

            break

        row = flatten_for_classify(ticket, thread_index)

        (

            total,

            tbc_old,

            tbc_new,

            tbc_b2b_old,

            tbc_b2b_new,

            tbc_b2c_old,

            tbc_b2c_new,

            zero_candidate_old,

            zero_candidate_new,

            margin_loss_old,

            margin_loss_new,

            below_threshold_old,

            below_threshold_new,

            allowlist_filtered_old,

            allowlist_filtered_new,

            other_old,

            other_new,

        ) = _compare_row(

            row,

            allow_old,

            allow_new,

            rule_specs_old=specs_old,

            rule_specs_new=specs_new,

            total=total,

            tbc_old=tbc_old,

            tbc_new=tbc_new,

            tbc_b2b_old=tbc_b2b_old,

            tbc_b2b_new=tbc_b2b_new,

            tbc_b2c_old=tbc_b2c_old,

            tbc_b2c_new=tbc_b2c_new,

            zero_candidate_old=zero_candidate_old,

            zero_candidate_new=zero_candidate_new,

            margin_loss_old=margin_loss_old,

            margin_loss_new=margin_loss_new,

            below_threshold_old=below_threshold_old,

            below_threshold_new=below_threshold_new,

            allowlist_filtered_old=allowlist_filtered_old,

            allowlist_filtered_new=allowlist_filtered_new,

            other_old=other_old,

            other_new=other_new,

            changed_rows=changed_rows,

            enrich_changed_rows=enrich_changed_rows,

        )



    return AllowlistCompareResult(

        total=total,

        tbc_old=tbc_old,

        tbc_new=tbc_new,

        changed_rows=changed_rows,

        zero_candidate_old=zero_candidate_old,

        zero_candidate_new=zero_candidate_new,

        allowlist_old_size=allowlist_old_size,

        allowlist_new_size=allowlist_new_size,

        tuples_merged=tuples_merged,

        tbc_b2b_old=tbc_b2b_old,

        tbc_b2b_new=tbc_b2b_new,

        tbc_b2c_old=tbc_b2c_old,

        tbc_b2c_new=tbc_b2c_new,

        margin_loss_old=margin_loss_old,

        margin_loss_new=margin_loss_new,

        below_threshold_old=below_threshold_old,

        below_threshold_new=below_threshold_new,

        allowlist_filtered_old=allowlist_filtered_old,

        allowlist_filtered_new=allowlist_filtered_new,

        other_old=other_old,

        other_new=other_new,

        rules_targeting_selected_old=_rules_targeting_selected(selected_tuples, specs_old),

        rules_targeting_selected_new=_rules_targeting_selected(selected_tuples, specs_new),

        bad_satisfaction_only=bad_satisfaction_only,

    )





def compare_allowlists_on_workbook(

    xlsx_path: Path,

    allow_old: AllowList,

    allow_new: AllowList,

    *,

    limit: int | None = None,

    allowlist_old_size: int = 0,

    allowlist_new_size: int = 0,

    tuples_merged: int = 0,

    rule_specs_old: tuple[RuleSpec, ...] | None = None,

    rule_specs_new: tuple[RuleSpec, ...] | None = None,

) -> AllowlistCompareResult:

    from cs_tickets.taxonomy import iter_workbook_master_rows



    default_rules = load_rule_specs()

    specs_old = rule_specs_old if rule_specs_old is not None else default_rules

    specs_new = rule_specs_new if rule_specs_new is not None else specs_old



    total = 0

    tbc_old = 0

    tbc_new = 0

    tbc_b2b_old = 0

    tbc_b2b_new = 0

    tbc_b2c_old = 0

    tbc_b2c_new = 0

    zero_candidate_old = 0

    zero_candidate_new = 0

    margin_loss_old = 0

    margin_loss_new = 0

    below_threshold_old = 0

    below_threshold_new = 0

    allowlist_filtered_old = 0

    allowlist_filtered_new = 0

    other_old = 0

    other_new = 0

    changed_rows: list[dict] = []



    for row in iter_workbook_master_rows(xlsx_path):

        if limit is not None and total >= limit:

            break

        (

            total,

            tbc_old,

            tbc_new,

            tbc_b2b_old,

            tbc_b2b_new,

            tbc_b2c_old,

            tbc_b2c_new,

            zero_candidate_old,

            zero_candidate_new,

            margin_loss_old,

            margin_loss_new,

            below_threshold_old,

            below_threshold_new,

            allowlist_filtered_old,

            allowlist_filtered_new,

            other_old,

            other_new,

        ) = _compare_row(

            row,

            allow_old,

            allow_new,

            rule_specs_old=specs_old,

            rule_specs_new=specs_new,

            total=total,

            tbc_old=tbc_old,

            tbc_new=tbc_new,

            tbc_b2b_old=tbc_b2b_old,

            tbc_b2b_new=tbc_b2b_new,

            tbc_b2c_old=tbc_b2c_old,

            tbc_b2c_new=tbc_b2c_new,

            zero_candidate_old=zero_candidate_old,

            zero_candidate_new=zero_candidate_new,

            margin_loss_old=margin_loss_old,

            margin_loss_new=margin_loss_new,

            below_threshold_old=below_threshold_old,

            below_threshold_new=below_threshold_new,

            allowlist_filtered_old=allowlist_filtered_old,

            allowlist_filtered_new=allowlist_filtered_new,

            other_old=other_old,

            other_new=other_new,

            changed_rows=changed_rows,

        )



    return AllowlistCompareResult(

        total=total,

        tbc_old=tbc_old,

        tbc_new=tbc_new,

        changed_rows=changed_rows,

        zero_candidate_old=zero_candidate_old,

        zero_candidate_new=zero_candidate_new,

        allowlist_old_size=allowlist_old_size,

        allowlist_new_size=allowlist_new_size,

        tuples_merged=tuples_merged,

        tbc_b2b_old=tbc_b2b_old,

        tbc_b2b_new=tbc_b2b_new,

        tbc_b2c_old=tbc_b2c_old,

        tbc_b2c_new=tbc_b2c_new,

        margin_loss_old=margin_loss_old,

        margin_loss_new=margin_loss_new,

        below_threshold_old=below_threshold_old,

        below_threshold_new=below_threshold_new,

        allowlist_filtered_old=allowlist_filtered_old,

        allowlist_filtered_new=allowlist_filtered_new,

        other_old=other_old,

        other_new=other_new,

    )





def compare_result_html(
    result: AllowlistCompareResult,
    *,
    stale: bool = False,
    plain_language: bool = False,
) -> str:

    if stale:

        return (

            '<p class="training-stale-banner" role="status">'

            "Selection changed — re-run preview to update metrics.</p>"

        )



    def pct(n: int) -> str:

        if not result.total:

            return "0.0%"

        return f"{100.0 * n / result.total:.1f}%"



    def delta(new: int, old: int) -> str:

        d = new - old

        sign = "+" if d > 0 else ""

        return f"{sign}{d}"



    if plain_language:
        rows = [
            (
                "Reference categories (pending save)",
                str(result.allowlist_old_size),
                str(result.allowlist_new_size),
                delta(result.allowlist_new_size, result.allowlist_old_size),
            ),
            ("Example rows in candidate workbook", "—", str(result.tuples_merged), ""),
            (
                "Rules targeting selected categories",
                str(result.rules_targeting_selected_old),
                str(result.rules_targeting_selected_new),
                delta(result.rules_targeting_selected_new, result.rules_targeting_selected_old),
            ),
            ("Total tickets", str(result.total), str(result.total), "0"),
            (
                "B2B manual review (TBC)",
                str(result.tbc_b2b_old),
                str(result.tbc_b2b_new),
                delta(result.tbc_b2b_new, result.tbc_b2b_old),
            ),
            ("B2B manual review %", pct(result.tbc_b2b_old), pct(result.tbc_b2b_new), ""),
            (
                "B2C manual review (TBC)",
                str(result.tbc_b2c_old),
                str(result.tbc_b2c_new),
                delta(result.tbc_b2c_new, result.tbc_b2c_old),
            ),
            ("B2C manual review %", pct(result.tbc_b2c_old), pct(result.tbc_b2c_new), ""),
            (
                "Manual review (TBC) combined",
                str(result.tbc_old),
                str(result.tbc_new),
                delta(result.tbc_new, result.tbc_old),
            ),
            ("Manual review %", pct(result.tbc_old), pct(result.tbc_new), ""),
            (
                "No rules matched (manual review)",
                str(result.zero_candidate_old),
                str(result.zero_candidate_new),
                delta(result.zero_candidate_new, result.zero_candidate_old),
            ),
            (
                "Rules blocked (manual review)",
                str(result.allowlist_filtered_old),
                str(result.allowlist_filtered_new),
                delta(result.allowlist_filtered_new, result.allowlist_filtered_old),
            ),
            (
                "Weak signal (manual review)",
                str(result.below_threshold_old),
                str(result.below_threshold_new),
                delta(result.below_threshold_new, result.below_threshold_old),
            ),
            (
                "Contested (manual review)",
                str(result.margin_loss_old),
                str(result.margin_loss_new),
                delta(result.margin_loss_new, result.margin_loss_old),
            ),
            (
                "Other manual review",
                str(result.other_old),
                str(result.other_new),
                delta(result.other_new, result.other_old),
            ),
        ]
        col_old, col_new = "Current", "With your selection"
        footnote = (
            '&ldquo;With your selection&rdquo; simulates categories and matching rules for your choices — '
            "<code>doc/</code> is unchanged until you save. "
            "Manual review (TBC) matches the audit classifier definition."
        )
    else:
        rows = [
            (
                "Allow-list tuples (pending commit)",
                str(result.allowlist_old_size),
                str(result.allowlist_new_size),
                delta(result.allowlist_new_size, result.allowlist_old_size),
            ),
            ("Exemplar rows in candidate workbook", "—", str(result.tuples_merged), ""),
            (
                "Rules targeting selected tuples",
                str(result.rules_targeting_selected_old),
                str(result.rules_targeting_selected_new),
                delta(result.rules_targeting_selected_new, result.rules_targeting_selected_old),
            ),
            ("Total rows", str(result.total), str(result.total), "0"),
            (
                "B2B TBC count",
                str(result.tbc_b2b_old),
                str(result.tbc_b2b_new),
                delta(result.tbc_b2b_new, result.tbc_b2b_old),
            ),
            ("B2B TBC %", pct(result.tbc_b2b_old), pct(result.tbc_b2b_new), ""),
            (
                "B2C TBC count",
                str(result.tbc_b2c_old),
                str(result.tbc_b2c_new),
                delta(result.tbc_b2c_new, result.tbc_b2c_old),
            ),
            ("B2C TBC %", pct(result.tbc_b2c_old), pct(result.tbc_b2c_new), ""),
            (
                "TBC count (combined, audit-style)",
                str(result.tbc_old),
                str(result.tbc_new),
                delta(result.tbc_new, result.tbc_old),
            ),
            ("TBC % (combined)", pct(result.tbc_old), pct(result.tbc_new), ""),
            (
                "No rules matched (manual review)",
                str(result.zero_candidate_old),
                str(result.zero_candidate_new),
                delta(result.zero_candidate_new, result.zero_candidate_old),
            ),
            (
                "Rules blocked (manual review)",
                str(result.allowlist_filtered_old),
                str(result.allowlist_filtered_new),
                delta(result.allowlist_filtered_new, result.allowlist_filtered_old),
            ),
            (
                "Weak signal (manual review)",
                str(result.below_threshold_old),
                str(result.below_threshold_new),
                delta(result.below_threshold_new, result.below_threshold_old),
            ),
            (
                "Contested (manual review)",
                str(result.margin_loss_old),
                str(result.margin_loss_new),
                delta(result.margin_loss_new, result.margin_loss_old),
            ),
            (
                "Other manual review",
                str(result.other_old),
                str(result.other_new),
                delta(result.other_new, result.other_old),
            ),
        ]
        col_old, col_new = "Old allow-list", "New allow-list"
        footnote = (
            'The &ldquo;New allow-list&rdquo; column uses a candidate workbook in your session only — '
            "<code>doc/</code> is unchanged until Commit. Preview includes proposed routing rules "
            "for selected categories. B2B and B2C TBC are split by <code>Tier1_Segment</code>. "
            "Combined TBC matches <code>tools/audit_classifier.py</code> (fallback or Tier4 contains "
            "&ldquo;tbc&rdquo;), not the portal download metadata sheet."
        )

    body = ""

    for label, old_v, new_v, d in rows:

        body += f"<tr><td>{label}</td><td>{old_v}</td><td>{new_v}</td><td>{d}</td></tr>"



    sample = ""

    if result.changed_rows and not plain_language:

        sample_rows = result.changed_rows[:20]

        sample = "<h3 class=\"section-header\">Changed tickets (sample)</h3><table class=\"preview-table\"><thead><tr><th>id</th><th>old Tier4</th><th>new Tier4</th></tr></thead><tbody>"

        for ch in sample_rows:

            sample += f"<tr><td>{_esc(ch['id'])}</td><td>{_esc(ch['old_tier4'])}</td><td>{_esc(ch['new_tier4'])}</td></tr>"

        sample += "</tbody></table>"

        if len(result.changed_rows) > 20:

            sample += f"<p class=\"meta\">Showing 20 of {len(result.changed_rows)} changed tickets.</p>"



    filter_note = ""

    if result.bad_satisfaction_only:

        filter_note = '<p class="meta">Preview limited to tickets with bad CSAT rating.</p>'



    return f"""

    <div class="training-preview">

        {filter_note}

        <table class="stats-table training-compare-table">

            <thead><tr><th>Metric</th><th>{col_old}</th><th>{col_new}</th><th>Delta</th></tr></thead>

            <tbody>{body}</tbody>

        </table>

        <p class="meta training-footnote">{footnote}</p>

        {sample}

    </div>"""





def _esc(v: object) -> str:

    if v is None:

        return ""

    s = str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return s[:200]


