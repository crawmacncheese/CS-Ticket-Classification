from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any, TypeAlias, cast

from cs_tickets.repo_paths import training_rules_path

TierTuple: TypeAlias = tuple[str, str, str, str, str]


@dataclass(frozen=True)
class RuleSpec:
    id: str
    tier: TierTuple
    weight: float
    any_tags: tuple[str, ...] = ()
    all_tags: tuple[str, ...] = ()
    any_subject: tuple[str, ...] = ()
    any_blob: tuple[str, ...] = ()
    exclude_blob: tuple[str, ...] = ()
    any_url: tuple[str, ...] = ()
    requires_b2b_print_context: bool = False
    source: str = ""
    exemplar_id: str = ""
    tuple_key: str = ""


def _tuple_strs(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"Expected list, got {type(value).__name__}")
    return tuple(str(item).lower() for item in value)


def _tier(value: Any) -> TierTuple:
    if not isinstance(value, list) or len(value) != 5:
        raise ValueError("Rule tier must be a 5-item list")
    return cast(TierTuple, tuple(str(item) for item in value))


def _rule_from_dict(raw: dict[str, Any]) -> RuleSpec:
    return RuleSpec(
        id=str(raw["id"]),
        tier=_tier(raw["tier"]),
        weight=float(raw["weight"]),
        any_tags=_tuple_strs(raw.get("any_tags")),
        all_tags=_tuple_strs(raw.get("all_tags")),
        any_subject=_tuple_strs(raw.get("any_subject")),
        any_blob=_tuple_strs(raw.get("any_blob")),
        exclude_blob=_tuple_strs(raw.get("exclude_blob")),
        any_url=_tuple_strs(raw.get("any_url")),
        requires_b2b_print_context=bool(raw.get("requires_b2b_print_context", False)),
        source=str(raw.get("source", "")),
        exemplar_id=str(raw.get("exemplar_id", "")),
        tuple_key=str(raw.get("tuple_key", "")),
    )


def _load_rules_file(path: Path) -> tuple[RuleSpec, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a list")
    rules: list[RuleSpec] = []
    for raw in data:
        if not isinstance(raw, dict):
            raise ValueError("Each rule must be an object")
        rules.append(_rule_from_dict(raw))
    return tuple(rules)


def _load_core_rules() -> tuple[RuleSpec, ...]:
    path = files("cs_tickets").joinpath("classifier_rules.json")
    return _load_rules_file(Path(path))


_override_rule_specs: tuple[RuleSpec, ...] | None = None


def set_active_rule_specs(rules: tuple[RuleSpec, ...] | None) -> None:
    """Portal/runtime override; None restores package + training_rules defaults."""
    global _override_rule_specs
    _override_rule_specs = rules
    load_rule_specs.cache_clear()


@lru_cache(maxsize=1)
def load_rule_specs() -> tuple[RuleSpec, ...]:
    if _override_rule_specs is not None:
        return _override_rule_specs
    core = _load_core_rules()
    path = training_rules_path()
    if not path.is_file():
        return core
    return core + _load_rules_file(path)


def reload_rule_specs() -> tuple[RuleSpec, ...]:
    load_rule_specs.cache_clear()
    return load_rule_specs()
