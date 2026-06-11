from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cs_tickets.classifier_rules import RuleSpec, TierTuple, load_rule_specs
from cs_tickets.classify import _tags_list
from cs_tickets.rule_coverage import has_rule_target, rule_target_tiers

DEFAULT_WEIGHT = 10.0
_COMPETITION_WEIGHT = 11.0
_SPECIFICITY_WEIGHT = 11.0
_CONTESTED_TIER3_WEIGHT = 12.0
_LIVE_CHAT_B2C_WEIGHT = 15.0
_LIVE_CHAT_B2B_WEIGHT = 16.0
_BROAD_ONLY_WEIGHT = 9.0
_CONTESTED_TIER3 = frozenset({"Complaint", "Junk", "Technical Bug"})

_GENERIC_TAGS = frozenset(
    {
        "miscellaneous",
        "other_departments",
        "customer_-_misc",
    }
)

_SUBJECT_NOISE = frozenset({"conversation with", "re:", "fw:"})

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "for",
        "is",
        "it",
        "my",
        "we",
        "you",
        "your",
        "our",
        "this",
        "that",
        "with",
        "from",
        "at",
        "be",
        "as",
        "by",
        "not",
        "no",
        "please",
        "thank",
        "thanks",
        "hi",
        "hello",
        "dear",
        "regards",
    }
)


@dataclass(frozen=True)
class ExemplarRuleSignals:
    """Proposed match signals for a training-generated rule."""

    tags: tuple[str, ...]
    any_tags: tuple[str, ...] = ()
    all_tags: tuple[str, ...] = ()
    any_subject: tuple[str, ...] = ()
    any_blob: tuple[str, ...] = ()
    exclude_blob: tuple[str, ...] = ()
    any_url: tuple[str, ...] = ()
    requires_b2b_print_context: bool = False
    blob_only: bool = False


@dataclass(frozen=True)
class GeneratedRule:
    spec: RuleSpec
    warnings: tuple[str, ...]


def tuple_key_for(tier: TierTuple) -> str:
    payload = "|".join(tier)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _exemplar_blob(exemplar: dict[str, str]) -> str:
    subject = (exemplar.get("subject") or "").lower()
    raw_subject = (exemplar.get("raw_subject") or "").lower()
    desc = (exemplar.get("description") or "").lower()
    return f"{subject} {raw_subject} {desc}"


def _exemplar_tags(exemplar: dict[str, str]) -> list[str]:
    tags_cell = exemplar.get("tags")
    if isinstance(tags_cell, str):
        return _tags_list(tags_cell)
    if tags_cell:
        return _tags_list(json.dumps(tags_cell))
    return []


def _specific_tags(tags: list[str]) -> tuple[str, ...]:
    out = [t for t in tags if t and t not in _GENERIC_TAGS]
    return tuple(sorted(set(out)))


def _subject_phrases(subject: str) -> tuple[str, ...]:
    s = subject.lower().strip()
    if not s or s in _SUBJECT_NOISE:
        return ()
    phrases: list[str] = []
    if len(s) >= 4 and s not in _SUBJECT_NOISE:
        phrases.append(s)
    for chunk in re.split(r"[^\w\s]+", s):
        chunk = chunk.strip()
        if len(chunk) >= 4 and chunk not in _STOPWORDS:
            phrases.append(chunk)
    return tuple(dict.fromkeys(phrases))[:3]


def _blob_phrases(blob: str, *, collision_phrases: frozenset[str]) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9][a-z0-9'-]{2,}", blob.lower())
    phrases: list[str] = []
    for i in range(len(words)):
        for length in (3, 2):
            if i + length > len(words):
                continue
            chunk = " ".join(words[i : i + length])
            if any(w in _STOPWORDS for w in chunk.split()):
                continue
            if len(chunk) < 4:
                continue
            if chunk in collision_phrases:
                continue
            phrases.append(chunk)
            if len(phrases) >= 4:
                return tuple(dict.fromkeys(phrases))
    return tuple(dict.fromkeys(phrases))


def _collision_phrases(rule_specs: tuple[RuleSpec, ...]) -> frozenset[str]:
    counts: dict[str, int] = {}
    for rule in rule_specs:
        for phrase in rule.any_blob:
            counts[phrase] = counts.get(phrase, 0) + 1
    return frozenset(p for p, n in counts.items() if n > 5)


def _url_fragments(url: str) -> tuple[str, ...]:
    u = url.lower()
    out: list[str] = []
    for frag in ("printsupport", "account.scmp.com"):
        if frag in u:
            out.append(frag)
    return tuple(out)


def _needs_b2b_print_context(exemplar: dict[str, str], tier: TierTuple) -> bool:
    if tier[0] != "B2B":
        return False
    tags = " ".join(_exemplar_tags(exemplar))
    url = (exemplar.get("url") or "").lower()
    return (
        "printsupport" in url
        or "printsupport" in tags
        or "print_subs" in tags
        or "print_subscription" in tags
    )


def _rule_id_for(tier: TierTuple) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (tier[3] or "tier").lower()).strip("_")
    seg = (tier[0] or "x").lower()
    return f"training.exemplar.{slug}.{seg}"


def _sibling_tier4_median_weight(
    tier: TierTuple,
    existing_rules: tuple[RuleSpec, ...],
) -> float | None:
    tier4 = tier[3]
    weights = sorted(r.weight for r in existing_rules if r.tier[3] == tier4)
    if not weights:
        return None
    mid = len(weights) // 2
    if len(weights) % 2:
        return weights[mid]
    return (weights[mid - 1] + weights[mid]) / 2.0


def _signal_group_count(signals: ExemplarRuleSignals) -> int:
    return sum(
        1
        for group in (
            signals.any_tags,
            signals.all_tags,
            signals.any_subject,
            signals.any_blob,
            signals.any_url,
        )
        if group
    )


def suggest_weight_for_exemplar(
    tier: TierTuple,
    signals: ExemplarRuleSignals,
    existing_rules: tuple[RuleSpec, ...],
) -> tuple[float, tuple[str, ...]]:
    """Suggest rule weight from core-rule patterns: sibling Tier4 median + bumps."""
    warnings: list[str] = []
    sibling = _sibling_tier4_median_weight(tier, existing_rules)
    weight = sibling if sibling is not None else DEFAULT_WEIGHT
    if sibling is not None:
        warnings.append(f"Tier4 sibling median weight {sibling:g}")

    tier3 = (tier[2] or "").strip()
    tier4_lower = (tier[3] or "").lower()
    segment = (tier[0] or "").strip().upper()

    if signals.all_tags or signals.exclude_blob:
        if weight < _SPECIFICITY_WEIGHT:
            weight = _SPECIFICITY_WEIGHT
            warnings.append(f"Multi-tag or exclude_blob rule; weight raised to {weight:g}")

    if "live chat" in tier4_lower:
        floor = _LIVE_CHAT_B2B_WEIGHT if segment == "B2B" else _LIVE_CHAT_B2C_WEIGHT
        if weight < floor:
            weight = floor
            warnings.append(f"Live-chat Tier4; weight raised to {weight:g}")

    if tier3 in _CONTESTED_TIER3 and _signal_group_count(signals) >= 2:
        if weight < _CONTESTED_TIER3_WEIGHT:
            weight = _CONTESTED_TIER3_WEIGHT
            warnings.append(f"Contested Tier3 ({tier3}); weight raised to {weight:g}")

    tag_set = set(signals.tags) | set(signals.any_tags) | set(signals.all_tags)
    for rule in existing_rules:
        if rule.tier == tier:
            continue
        rule_tags = set(rule.any_tags) | set(rule.all_tags)
        if tag_set & rule_tags:
            if weight < _COMPETITION_WEIGHT:
                weight = _COMPETITION_WEIGHT
                warnings.append(
                    f"Tag overlap with rule {rule.id}; weight raised to {weight:g}"
                )
            break

    if signals.blob_only and weight > _BROAD_ONLY_WEIGHT:
        weight = _BROAD_ONLY_WEIGHT
        warnings.append(f"Blob-only rule; weight capped at {weight:g}")

    return weight, tuple(warnings)


def generate_rule_from_exemplar(
    exemplar: dict[str, str],
    tier: TierTuple,
    *,
    existing_targets: dict[TierTuple, tuple[str, ...]] | None = None,
    existing_rules: tuple[RuleSpec, ...] | None = None,
) -> GeneratedRule | None:
    rules = existing_rules if existing_rules is not None else load_rule_specs()
    if existing_targets is not None and tier in existing_targets:
        return None
    if has_rule_target(tier, json_rules=rules):
        return None

    tags = _specific_tags(_exemplar_tags(exemplar))
    subject = (exemplar.get("subject") or "").strip()
    subject_phrases = _subject_phrases(subject)
    blob = _exemplar_blob(exemplar)
    blob_phrases = _blob_phrases(blob, collision_phrases=_collision_phrases(rules))
    url_frags = _url_fragments(exemplar.get("url") or "")

    warnings: list[str] = []

    any_tags: tuple[str, ...] = ()
    all_tags: tuple[str, ...] = ()
    any_subject: tuple[str, ...] = ()
    any_blob: tuple[str, ...] = ()
    any_url: tuple[str, ...] = ()
    blob_only = False

    if len(tags) >= 2:
        all_tags = tags[:]
        any_blob = blob_phrases[:2]
    elif len(tags) == 1 and subject_phrases:
        any_tags = tags
        any_subject = subject_phrases[:2]
    elif len(tags) >= 1 and blob_phrases:
        any_tags = tags
        any_blob = blob_phrases[:2]
    elif len(blob_phrases) >= 2:
        any_blob = blob_phrases[:4]
        blob_only = True
        warnings.append("Blob-only rule — review for over-breadth")
    else:
        return None

    # Only use URL fragments when they also appear in ticket text (NDJSON rows often lack url).
    blob_url_frags = tuple(f for f in url_frags if f in blob)
    if blob_url_frags:
        if any_tags or all_tags or any_subject:
            any_blob = tuple(dict.fromkeys((*any_blob, *blob_url_frags)))
        else:
            any_url = blob_url_frags

    requires_b2b = _needs_b2b_print_context(exemplar, tier)

    rule_signals = ExemplarRuleSignals(
        tags=tags,
        any_tags=any_tags,
        all_tags=all_tags,
        any_subject=any_subject,
        any_blob=any_blob,
        any_url=any_url,
        requires_b2b_print_context=requires_b2b,
        blob_only=blob_only,
    )
    weight, weight_warnings = suggest_weight_for_exemplar(tier, rule_signals, rules)
    warnings.extend(weight_warnings)

    if tier[0] == "B2B" and not requires_b2b:
        url = (exemplar.get("url") or "").lower()
        if "printsupport" in url:
            warnings.append("B2B exemplar without print tags; rule may not fire on printsupport queue")

    exemplar_id = str(exemplar.get("id") or "")
    spec = RuleSpec(
        id=_rule_id_for(tier),
        tier=tier,
        weight=weight,
        any_tags=any_tags,
        all_tags=all_tags,
        any_subject=any_subject,
        any_blob=any_blob,
        any_url=any_url,
        requires_b2b_print_context=requires_b2b,
        source="training_commit",
        exemplar_id=exemplar_id,
        tuple_key=tuple_key_for(tier),
    )
    return GeneratedRule(spec=spec, warnings=tuple(warnings))


def rule_spec_to_dict(spec: RuleSpec) -> dict:
    out: dict = {
        "id": spec.id,
        "tier": list(spec.tier),
        "weight": spec.weight,
    }
    if spec.any_tags:
        out["any_tags"] = list(spec.any_tags)
    if spec.all_tags:
        out["all_tags"] = list(spec.all_tags)
    if spec.any_subject:
        out["any_subject"] = list(spec.any_subject)
    if spec.any_blob:
        out["any_blob"] = list(spec.any_blob)
    if spec.exclude_blob:
        out["exclude_blob"] = list(spec.exclude_blob)
    if spec.any_url:
        out["any_url"] = list(spec.any_url)
    if spec.requires_b2b_print_context:
        out["requires_b2b_print_context"] = True
    if spec.source:
        out["source"] = spec.source
    if spec.exemplar_id:
        out["exemplar_id"] = spec.exemplar_id
    if spec.tuple_key:
        out["tuple_key"] = spec.tuple_key
    return out


def upsert_training_rules(path: Path, rules: list[GeneratedRule]) -> int:
    """Replace entries with matching tuple_key; append new. Return count upserted."""
    if not rules:
        return 0
    existing: list[dict] = []
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            raise ValueError(f"{path} must contain a list")

    by_key = {str(item.get("tuple_key", "")): i for i, item in enumerate(existing) if item.get("tuple_key")}
    added = 0
    for generated in rules:
        entry = rule_spec_to_dict(generated.spec)
        key = generated.spec.tuple_key
        if key in by_key:
            existing[by_key[key]] = entry
        else:
            by_key[key] = len(existing)
            existing.append(entry)
        added += 1

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".json")
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
            f.write("\n")
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return added
