from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cs_tickets.classifier_rules import RuleSpec, TierTuple
from cs_tickets.taxonomy import AllowList

CoverageStatus = Literal["routable", "allow_only", "blocked"]
TrainingBadge = Literal["already_routable", "needs_rule"]


@dataclass(frozen=True)
class TupleCoverage:
    tier: TierTuple
    status: CoverageStatus
    rule_ids: tuple[str, ...]


def scored_targets_from_source(path: Path) -> set[TierTuple]:
    """AST scrape of ``add((tier...), weight)`` calls in classify.py."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[TierTuple] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "add"
            and node.args
        ):
            continue
        arg = node.args[0]
        if (
            isinstance(arg, ast.Tuple)
            and len(arg.elts) == 5
            and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in arg.elts)
        ):
            out.add(tuple(e.value for e in arg.elts))
    return out


def _default_classify_path() -> Path:
    return Path(__file__).resolve().parent / "classify.py"


def computed_rule_targets(classify_py: Path | None = None) -> dict[TierTuple, tuple[str, ...]]:
    path = classify_py or _default_classify_path()
    return {tier: ("computed",) for tier in sorted(scored_targets_from_source(path))}


def rule_target_tiers(rule_specs: tuple[RuleSpec, ...]) -> dict[TierTuple, tuple[str, ...]]:
    out: dict[TierTuple, list[str]] = {}
    for rule in rule_specs:
        out.setdefault(rule.tier, []).append(rule.id)
    return {tier: tuple(ids) for tier, ids in out.items()}


def _all_rule_ids_for_tier(
    tier: TierTuple,
    *,
    json_rules: tuple[RuleSpec, ...],
    computed_targets: dict[TierTuple, tuple[str, ...]],
) -> tuple[str, ...]:
    ids: list[str] = []
    for rule in json_rules:
        if rule.tier == tier:
            ids.append(rule.id)
    ids.extend(computed_targets.get(tier, ()))
    return tuple(ids)


def has_rule_target(
    tier: TierTuple,
    *,
    json_rules: tuple[RuleSpec, ...],
    computed_targets: dict[TierTuple, tuple[str, ...]] | None = None,
) -> bool:
    computed = computed_targets if computed_targets is not None else computed_rule_targets()
    return tier in rule_target_tiers(json_rules) or tier in computed


def training_routing_badge(
    tier: TierTuple,
    *,
    json_rules: tuple[RuleSpec, ...],
    computed_targets: dict[TierTuple, tuple[str, ...]] | None = None,
) -> TrainingBadge:
    if has_rule_target(tier, json_rules=json_rules, computed_targets=computed_targets):
        return "already_routable"
    return "needs_rule"


def training_routing_badge_label(badge: TrainingBadge) -> str:
    if badge == "already_routable":
        return "Already routable"
    return "Needs routing rule"


def tuple_rule_coverage(
    tier: TierTuple,
    allow: AllowList,
    *,
    json_rules: tuple[RuleSpec, ...],
    computed_targets: dict[TierTuple, tuple[str, ...]] | None = None,
) -> TupleCoverage:
    computed = computed_targets if computed_targets is not None else computed_rule_targets()
    rule_ids = _all_rule_ids_for_tier(tier, json_rules=json_rules, computed_targets=computed)
    has_target = bool(rule_ids)
    in_allow = tier in allow

    if has_target and in_allow:
        status: CoverageStatus = "routable"
    elif has_target and not in_allow:
        status = "blocked"
    else:
        status = "allow_only"
    return TupleCoverage(tier=tier, status=status, rule_ids=rule_ids)
