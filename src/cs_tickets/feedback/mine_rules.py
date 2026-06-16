from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Literal

from cs_tickets.classifier_rules import RuleSpec, load_rule_specs
from cs_tickets.classify import _tags_list, classify_row
from cs_tickets.feedback.ids import normalize_ticket_id
from cs_tickets.feedback.models import MineConfig, RuleProposal
from cs_tickets.schema import TIER_FALLBACK_B2C_TBC, TIER_FALLBACK_DEFAULT_TBC
from cs_tickets.taxonomy import AllowList

_MAX_SUBJECT_PREFIX = 40
_MAX_PROPOSALS = 200
_CLUSTER_OVERLAP_RATIO = 0.85
_KIND_STRENGTH = {"all_tags": 4, "any_tags": 3, "any_subject": 2, "any_blob": 1}


def _tier_tuple(row: dict[str, object]) -> tuple[str, str, str, str, str]:
    from cs_tickets.schema import TIER_COLUMNS

    parts = [str(row.get(col) or "").strip() for col in TIER_COLUMNS[:4]]
    granular = str(row.get("Granular_Tech_UI_Type") or "").strip() or "N/A"
    return (*parts, granular)


def _row_id(row: dict[str, object]) -> str:
    return normalize_ticket_id(row.get("id"))


def _is_tbc_tuple(tier: tuple[str, str, str, str, str]) -> bool:
    if tier in (TIER_FALLBACK_DEFAULT_TBC, TIER_FALLBACK_B2C_TBC):
        return True
    return "tbc" in tier[3].lower()


def _row_tags(row: dict[str, object]) -> frozenset[str]:
    cell = row.get("tags")
    if isinstance(cell, str):
        return frozenset(_tags_list(cell))
    return frozenset()


def _row_blob(row: dict[str, object]) -> str:
    subject = str(row.get("subject") or "").lower()
    raw_subject = str(row.get("raw_subject") or "").lower()
    desc = str(row.get("description") or "").lower()
    return f"{subject} {raw_subject} {desc}"


def _subject_prefix(row: dict[str, object]) -> str:
    subject = str(row.get("subject") or row.get("raw_subject") or "").strip().lower()
    if not subject:
        return ""
    clipped = subject[:_MAX_SUBJECT_PREFIX].rstrip()
    if len(subject) > _MAX_SUBJECT_PREFIX and " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped


def _suggest_weight(support: int, purity: float, *, tag_only: bool) -> float:
    bonus = max(0.0, (purity - 0.85) * 10.0)
    weight = 10.0 + math.log2(max(support, 1)) + bonus + (1.0 if tag_only else 0.0)
    return min(round(weight, 1), 14.0)


def _slug(*parts: str) -> str:
    raw = ".".join(p for p in parts if p)
    slug = re.sub(r"[^a-z0-9._-]+", "_", raw.lower()).strip("._")
    return slug[:80] or "rule"


def _dominant_tuple(
    rows: list[dict[str, object]],
) -> tuple[tuple[str, str, str, str, str], int, float] | None:
    if not rows:
        return None
    counts: Counter[tuple[str, str, str, str, str]] = Counter(_tier_tuple(r) for r in rows)
    tier, support = counts.most_common(1)[0]
    purity = support / len(rows)
    return tier, support, purity


def _collect_evidence(rows: list[dict[str, object]], limit: int) -> tuple[str, ...]:
    out: list[str] = []
    for row in rows:
        rid = _row_id(row)
        if rid and rid not in out:
            out.append(rid)
        if len(out) >= limit:
            break
    return tuple(out)


def _existing_rule_status(
    existing: tuple[RuleSpec, ...],
    *,
    tier: tuple[str, str, str, str, str],
    any_tags: tuple[str, ...] = (),
    all_tags: tuple[str, ...] = (),
    any_subject: tuple[str, ...] = (),
    any_blob: tuple[str, ...] = (),
) -> Literal["duplicate", "conflict"] | None:
    for rule in existing:
        same_tier = rule.tier == tier
        if all_tags and frozenset(rule.all_tags) == frozenset(all_tags):
            return "duplicate" if same_tier else "conflict"
        if any_tags and frozenset(rule.any_tags) == frozenset(any_tags):
            return "duplicate" if same_tier else "conflict"
        if any_subject and frozenset(rule.any_subject) == frozenset(any_subject):
            return "duplicate" if same_tier else "conflict"
        if any_blob and frozenset(rule.any_blob) == frozenset(any_blob):
            return "duplicate" if same_tier else "conflict"
    return None


def _cluster_already_classified(
    rows: list[dict[str, object]],
    tier: tuple[str, str, str, str, str],
    allow: AllowList,
) -> bool:
    for row in rows:
        predicted = classify_row(dict(row), allow)
        if predicted != tier:
            return False
    return True


def _ngrams(words: list[str], n: int) -> set[str]:
    if len(words) < n:
        return set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def _row_matches_proposal(row: dict[str, object], proposal: RuleProposal) -> bool:
    if _tier_tuple(row) != proposal.tier:
        return False
    if proposal.all_tags:
        tags = _row_tags(row)
        return all(tag in tags for tag in proposal.all_tags)
    if proposal.any_tags:
        return proposal.any_tags[0] in _row_tags(row)
    if proposal.any_subject:
        return _subject_prefix(row) == proposal.any_subject[0]
    if proposal.any_blob:
        return proposal.any_blob[0] in _row_blob(row)
    return False


def _proposal_matching_ids(
    proposal: RuleProposal,
    rows: list[dict[str, object]],
) -> frozenset[str]:
    return frozenset(
        rid
        for row in rows
        if (rid := _row_id(row)) and _row_matches_proposal(row, proposal)
    )


def _proposal_strength(proposal: RuleProposal) -> tuple[float, float, float, float, str]:
    signal_count = len(
        proposal.all_tags or proposal.any_tags or proposal.any_subject or proposal.any_blob
    )
    return (
        float(proposal.support),
        float(_KIND_STRENGTH.get(proposal.kind, 0)),
        proposal.purity,
        float(signal_count),
        proposal.proposal_id,
    )


def _ticket_sets_overlap(
    left: frozenset[str],
    right: frozenset[str],
    *,
    overlap_ratio: float,
) -> bool:
    if not left or not right:
        return False
    if left == right or left <= right or right <= left:
        return True
    union = len(left | right)
    if union == 0:
        return False
    return len(left & right) / union >= overlap_ratio


def dedupe_rule_proposals_by_cluster(
    proposals: list[RuleProposal],
    rows: list[dict[str, object]],
    *,
    overlap_ratio: float = _CLUSTER_OVERLAP_RATIO,
) -> list[RuleProposal]:
    """Keep only the strongest proposal when ticket sets overlap for the same tier."""
    id_sets = {proposal.proposal_id: _proposal_matching_ids(proposal, rows) for proposal in proposals}
    ranked = sorted(proposals, key=_proposal_strength, reverse=True)
    kept: list[RuleProposal] = []
    kept_sets: list[frozenset[str]] = []
    kept_tiers: list[tuple[str, str, str, str, str]] = []
    for proposal in ranked:
        ids = id_sets[proposal.proposal_id]
        if not ids:
            continue
        overlaps = any(
            proposal.tier == tier
            and _ticket_sets_overlap(ids, kept_ids, overlap_ratio=overlap_ratio)
            for kept_ids, tier in zip(kept_sets, kept_tiers, strict=True)
        )
        if overlaps:
            continue
        kept.append(proposal)
        kept_sets.append(ids)
        kept_tiers.append(proposal.tier)
    return kept


def _mine_all_tags(
    rows: list[dict[str, object]],
    existing: tuple[RuleSpec, ...],
    allow: AllowList,
    cfg: MineConfig,
    seen: set[str],
) -> list[RuleProposal]:
    groups: dict[tuple[frozenset[str], tuple[str, str, str, str, str]], list[dict[str, object]]] = (
        defaultdict(list)
    )
    for row in rows:
        tags = _row_tags(row)
        if not tags:
            continue
        tier = _tier_tuple(row)
        groups[(tags, tier)].append(row)

    out: list[RuleProposal] = []
    for (tags, tier), bucket in groups.items():
        if len(bucket) < cfg.min_support:
            continue
        purity = 1.0
        key = f"all_tags:{sorted(tags)}:{tier}"
        if key in seen:
            continue
        if cfg.skip_already_classified and _cluster_already_classified(bucket, tier, allow):
            continue
        status = _existing_rule_status(existing, tier=tier, all_tags=tuple(sorted(tags)))
        if status in ("duplicate", "conflict"):
            continue
        seen.add(key)
        tag_list = tuple(sorted(tags))
        out.append(
            RuleProposal(
                proposal_id=f"rule.{_slug('all_tags', *tag_list[:3], tier[3])}",
                kind="all_tags",
                tier=tier,
                weight=_suggest_weight(len(bucket), purity, tag_only=True),
                support=len(bucket),
                purity=purity,
                all_tags=tag_list,
                evidence_ids=_collect_evidence(bucket, cfg.max_evidence),
            )
        )
    return out


def _mine_any_tags(
    rows: list[dict[str, object]],
    existing: tuple[RuleSpec, ...],
    allow: AllowList,
    cfg: MineConfig,
    seen: set[str],
) -> list[RuleProposal]:
    by_tag: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        for tag in _row_tags(row):
            by_tag[tag].append(row)

    out: list[RuleProposal] = []
    for tag, bucket in by_tag.items():
        dominant = _dominant_tuple(bucket)
        if dominant is None:
            continue
        tier, support, purity = dominant
        if support < cfg.min_support or purity < cfg.tag_any_purity:
            continue
        key = f"any_tags:{tag}:{tier}"
        if key in seen:
            continue
        matching = [r for r in bucket if _tier_tuple(r) == tier]
        if cfg.skip_already_classified and _cluster_already_classified(matching, tier, allow):
            continue
        status = _existing_rule_status(existing, tier=tier, any_tags=(tag,))
        if status in ("duplicate", "conflict"):
            continue
        seen.add(key)
        out.append(
            RuleProposal(
                proposal_id=f"rule.{_slug('any_tags', tag, tier[3])}",
                kind="any_tags",
                tier=tier,
                weight=_suggest_weight(support, purity, tag_only=True),
                support=support,
                purity=round(purity, 3),
                any_tags=(tag,),
                evidence_ids=_collect_evidence(matching, cfg.max_evidence),
            )
        )
    return out


def _mine_subject_prefixes(
    rows: list[dict[str, object]],
    existing: tuple[RuleSpec, ...],
    allow: AllowList,
    cfg: MineConfig,
    seen: set[str],
) -> list[RuleProposal]:
    groups: dict[tuple[str, tuple[str, str, str, str, str]], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        prefix = _subject_prefix(row)
        if len(prefix) < 8:
            continue
        groups[(prefix, _tier_tuple(row))].append(row)

    out: list[RuleProposal] = []
    for (prefix, tier), bucket in groups.items():
        if len(bucket) < cfg.min_support:
            continue
        purity = len(bucket) / len(bucket)
        key = f"subject:{prefix}:{tier}"
        if key in seen:
            continue
        if cfg.skip_already_classified and _cluster_already_classified(bucket, tier, allow):
            continue
        status = _existing_rule_status(existing, tier=tier, any_subject=(prefix,))
        if status in ("duplicate", "conflict"):
            continue
        seen.add(key)
        out.append(
            RuleProposal(
                proposal_id=f"rule.{_slug('subject', prefix[:24], tier[3])}",
                kind="any_subject",
                tier=tier,
                weight=_suggest_weight(len(bucket), purity, tag_only=False),
                support=len(bucket),
                purity=purity,
                any_subject=(prefix,),
                evidence_ids=_collect_evidence(bucket, cfg.max_evidence),
            )
        )
    return out


def _mine_blob_phrases(
    rows: list[dict[str, object]],
    existing: tuple[RuleSpec, ...],
    allow: AllowList,
    cfg: MineConfig,
    seen: set[str],
) -> list[RuleProposal]:
    phrase_rows: dict[tuple[str, tuple[str, str, str, str, str]], list[dict[str, object]]] = (
        defaultdict(list)
    )
    for row in rows:
        blob = _row_blob(row)
        words = re.findall(r"[a-z0-9]{3,}", blob)
        if len(words) < 2:
            continue
        tier = _tier_tuple(row)
        phrases: set[str] = set()
        for n in (2, 3):
            phrases |= _ngrams(words, n)
        for phrase in phrases:
            if len(phrase) < 8:
                continue
            phrase_rows[(phrase, tier)].append(row)

    scored: list[tuple[int, str, tuple[str, str, str, str, str], list[dict[str, object]]]] = []
    for (phrase, tier), bucket in phrase_rows.items():
        if len(bucket) < cfg.min_support:
            continue
        scored.append((len(bucket), phrase, tier, bucket))
    scored.sort(reverse=True)

    out: list[RuleProposal] = []
    for support, phrase, tier, bucket in scored:
        key = f"blob:{phrase}:{tier}"
        if key in seen:
            continue
        matching = [r for r in bucket if phrase in _row_blob(r)]
        purity = len({ _row_id(r) for r in matching if _row_id(r) }) / max(len(bucket), 1)
        if purity < cfg.min_purity:
            continue
        if cfg.skip_already_classified and _cluster_already_classified(matching, tier, allow):
            continue
        status = _existing_rule_status(existing, tier=tier, any_blob=(phrase,))
        if status in ("duplicate", "conflict"):
            continue
        seen.add(key)
        out.append(
            RuleProposal(
                proposal_id=f"rule.{_slug('blob', phrase[:20], tier[3])}",
                kind="any_blob",
                tier=tier,
                weight=_suggest_weight(support, purity, tag_only=False),
                support=support,
                purity=round(purity, 3),
                any_blob=(phrase,),
                evidence_ids=_collect_evidence(matching, cfg.max_evidence),
            )
        )
        if len(out) >= 50:
            break
    return out


def mine_rule_proposals(
    rows: list[dict[str, object]],
    allow: AllowList,
    *,
    config: MineConfig | None = None,
    existing_rules: tuple[RuleSpec, ...] | None = None,
) -> tuple[RuleProposal, ...]:
    """Cluster labeled rows into RuleSpec-compatible proposals."""
    cfg = config or MineConfig()
    existing = existing_rules if existing_rules is not None else load_rule_specs()

    eligible = [r for r in rows if _row_id(r) and any(_tier_tuple(r)[:4])]
    if cfg.exclude_tbc:
        eligible = [r for r in eligible if not _is_tbc_tuple(_tier_tuple(r))]

    seen: set[str] = set()
    proposals: list[RuleProposal] = []
    for miner in (_mine_all_tags, _mine_any_tags, _mine_subject_prefixes, _mine_blob_phrases):
        proposals.extend(miner(eligible, existing, allow, cfg, seen))
        if len(proposals) >= _MAX_PROPOSALS * 2:
            break

    proposals = dedupe_rule_proposals_by_cluster(proposals, eligible)
    proposals.sort(key=lambda p: (-p.support, -p.purity, p.proposal_id))
    return tuple(proposals[:_MAX_PROPOSALS])


def count_already_classified(rows: list[dict[str, object]], allow: AllowList) -> int:
    total = 0
    for row in rows:
        cs = _tier_tuple(row)
        if not any(cs[:4]) or _is_tbc_tuple(cs):
            continue
        if classify_row(dict(row), allow) == cs:
            total += 1
    return total
