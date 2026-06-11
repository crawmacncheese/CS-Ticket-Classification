from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from cs_tickets.classify import classify_row_with_explanation, tbc_reason
from cs_tickets.classifier_rules import load_rule_specs
from cs_tickets.flatten import flatten_ticket
from cs_tickets.rule_coverage import computed_rule_targets, rule_target_tiers
from cs_tickets.schema import PIPELINE_FALLBACK_TIER_TUPLES
from cs_tickets.taxonomy import load_allowlist


def _tags(tags_cell: str) -> list[str]:
    try:
        value = json.loads(tags_cell or "[]")
    except json.JSONDecodeError:
        return [tags_cell] if tags_cell else []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--taxonomy", default=Path("doc/Taxonomy.csv"), type=Path)
    parser.add_argument("--workbook", default=Path("doc/CS_ticket_new_categorizations.xlsx"), type=Path)
    parser.add_argument("--classifier", default=Path("src/cs_tickets/classify.py"), type=Path)
    args = parser.parse_args()

    allow = load_allowlist(args.taxonomy, args.workbook)
    rules = load_rule_specs()
    computed = computed_rule_targets(args.classifier)
    json_targets = set(rule_target_tiers(rules))
    scored = set(computed) | json_targets | set(PIPELINE_FALLBACK_TIER_TUPLES)
    unreachable = sorted(allow.tuples - scored)

    total = 0
    fallback = 0
    tier_counts: Counter[tuple[str, str, str, str, str]] = Counter()
    tbc_tags: Counter[str] = Counter()
    tbc_subjects: Counter[str] = Counter()
    tbc_reasons: Counter[str] = Counter()
    margin_pairs: Counter[tuple[str, str]] = Counter()

    with args.input.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = flatten_ticket(json.loads(line))
            decision = classify_row_with_explanation(row, allow)
            total += 1
            tier_counts[decision.tier] += 1
            if decision.fallback_used or "tbc" in decision.tier[3].lower():
                fallback += 1
                reason = tbc_reason(decision)
                tbc_reasons[reason] += 1
                if reason == "lost_margin" and len(decision.candidates) >= 2:
                    best_t, best_s = decision.candidates[0]
                    second_t, second_s = decision.candidates[1]
                    pair = (
                        f"{best_t[0]} {best_t[3]} ({best_s})",
                        f"{second_t[0]} {second_t[3]} ({second_s})",
                    )
                    margin_pairs[pair] += 1
                tbc_tags.update(_tags(str(row.get("tags") or "")))
                subject = str(row.get("subject") or "").strip()
                if subject:
                    tbc_subjects[subject[:120]] += 1

    print(f"rows: {total}")
    if total:
        print(f"tbc_or_fallback: {fallback} ({fallback / total:.1%})")
    else:
        print("tbc_or_fallback: 0")
    print(f"allow_tuples: {len(allow.tuples)}")
    print(f"scored_tuples: {len(scored)}")
    print(f"unreachable_allow_tuples: {len(unreachable)}")
    if unreachable[:10]:
        print("unreachable_allow_sample:")
        for tier in unreachable[:10]:
            print(f"  {' | '.join(tier)}")
    print("tbc_reason_buckets:")
    for reason, count in tbc_reasons.most_common():
        print(f"  {count}: {reason}")
    print("top_margin_loss_pairs:")
    for (a, b), count in margin_pairs.most_common(15):
        print(f"  TBC margin-loss: {a} vs {b} — {count} tickets")
    print("top_tiers:")
    for tier, count in tier_counts.most_common(15):
        print(f"  {count}: {' | '.join(tier)}")
    print("top_tbc_tags:")
    for tag, count in tbc_tags.most_common(20):
        print(f"  {count}: {tag}")
    print("top_tbc_subjects:")
    for subject, count in tbc_subjects.most_common(20):
        print(f"  {count}: {subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
