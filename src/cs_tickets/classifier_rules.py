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
    any_requester: tuple[str, ...] = ()
    any_requester_domain: tuple[str, ...] = ()
    requires_b2b_print_context: bool = False
    enabled: bool = True
    override: bool = False
    display_name: str = ""
    notes: str = ""
    created_at: str = ""
    disabled_at: str = ""
    replaced_by: str = ""
    source_message: str = ""
    source: str = ""
    exemplar_id: str = ""
    tuple_key: str = ""


def _tuple_strs(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    # Be tolerant: compilers (LLM or heuristics) may emit a single string instead of a list.
    if isinstance(value, str):
        s = value.strip()
        return (s.lower(),) if s else ()
    if not isinstance(value, list):
        raise ValueError(f"Expected list, got {type(value).__name__}")
    return tuple(str(item).lower() for item in value if str(item).strip())


def _tier(value: Any) -> TierTuple:
    if not isinstance(value, list) or len(value) != 5:
        raise ValueError("Rule tier must be a 5-item list")
    return cast(TierTuple, tuple(str(item) for item in value))


def _rule_from_dict(raw: dict[str, Any]) -> RuleSpec:
    enabled_raw = raw.get("enabled", True)
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
        any_requester=_tuple_strs(raw.get("any_requester")),
        any_requester_domain=_tuple_strs(raw.get("any_requester_domain")),
        requires_b2b_print_context=bool(raw.get("requires_b2b_print_context", False)),
        enabled=enabled_raw is not False,
        override=bool(raw.get("override", False)),
        display_name=str(raw.get("display_name", "")),
        notes=str(raw.get("notes", "")),
        created_at=str(raw.get("created_at", "")),
        disabled_at=str(raw.get("disabled_at", "")),
        replaced_by=str(raw.get("replaced_by", "")),
        source_message=str(raw.get("source_message", "")),
        source=str(raw.get("source", "")),
        exemplar_id=str(raw.get("exemplar_id", "")),
        tuple_key=str(raw.get("tuple_key", "")),
    )


def rule_spec_to_json(spec: RuleSpec) -> dict[str, Any]:
    """Serialize a RuleSpec for live classifier_rules.json."""
    item: dict[str, Any] = {
        "id": spec.id,
        "tier": list(spec.tier),
        "weight": spec.weight,
    }
    if spec.all_tags:
        item["all_tags"] = list(spec.all_tags)
    if spec.any_tags:
        item["any_tags"] = list(spec.any_tags)
    if spec.any_subject:
        item["any_subject"] = list(spec.any_subject)
    if spec.any_blob:
        item["any_blob"] = list(spec.any_blob)
    if spec.exclude_blob:
        item["exclude_blob"] = list(spec.exclude_blob)
    if spec.any_url:
        item["any_url"] = list(spec.any_url)
    if spec.any_requester:
        item["any_requester"] = list(spec.any_requester)
    if spec.any_requester_domain:
        item["any_requester_domain"] = list(spec.any_requester_domain)
    if spec.requires_b2b_print_context:
        item["requires_b2b_print_context"] = True
    if spec.enabled is False:
        item["enabled"] = False
    if spec.override:
        item["override"] = True
    if spec.display_name:
        item["display_name"] = spec.display_name
    if spec.notes:
        item["notes"] = spec.notes
    if spec.created_at:
        item["created_at"] = spec.created_at
    if spec.disabled_at:
        item["disabled_at"] = spec.disabled_at
    if spec.replaced_by:
        item["replaced_by"] = spec.replaced_by
    if spec.source_message:
        item["source_message"] = spec.source_message
    if spec.source:
        item["source"] = spec.source
    if spec.exemplar_id:
        item["exemplar_id"] = spec.exemplar_id
    if spec.tuple_key:
        item["tuple_key"] = spec.tuple_key
    return item


def rule_has_match_conditions(spec: RuleSpec) -> bool:
    return bool(
        spec.any_tags
        or spec.all_tags
        or spec.any_subject
        or spec.any_blob
        or spec.any_url
        or spec.any_requester
        or spec.any_requester_domain
        or spec.requires_b2b_print_context
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
