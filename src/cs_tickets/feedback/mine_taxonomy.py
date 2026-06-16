from __future__ import annotations

import re
from collections import Counter, defaultdict

from cs_tickets.feedback.ids import normalize_ticket_id
from cs_tickets.feedback.models import MineConfig, TaxonomyProposal
from cs_tickets.schema import TIER_COLUMNS
from cs_tickets.taxonomy import AllowList, novelty_type_for_tuple


def _tier_tuple(row: dict[str, object]) -> tuple[str, str, str, str, str]:
    parts = [str(row.get(col) or "").strip() for col in TIER_COLUMNS[:4]]
    granular = str(row.get("Granular_Tech_UI_Type") or "").strip() or "N/A"
    return (*parts, granular)


def _row_id(row: dict[str, object]) -> str:
    return normalize_ticket_id(row.get("id"))


def _proposal_slug(tier: tuple[str, str, str, str, str]) -> str:
    raw = "-".join(tier)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-").lower()
    return slug[:72] or "tuple"


def mine_taxonomy_proposals(
    rows: list[dict[str, object]],
    allow: AllowList,
    *,
    config: MineConfig | None = None,
) -> tuple[TaxonomyProposal, ...]:
    """Detect CS tier tuples not present in the current allow-list."""
    cfg = config or MineConfig()
    counts: Counter[tuple[str, str, str, str, str]] = Counter()
    examples: dict[tuple[str, str, str, str, str], list[str]] = defaultdict(list)

    for row in rows:
        tier = _tier_tuple(row)
        if not any(tier[:4]):
            continue
        rid = _row_id(row)
        if not rid:
            continue
        counts[tier] += 1
        bucket = examples[tier]
        if len(bucket) < cfg.max_evidence:
            bucket.append(rid)

    proposals: list[TaxonomyProposal] = []
    for tier, count in counts.most_common():
        if tier in allow:
            continue
        if cfg.min_support and count < 1:
            continue
        proposals.append(
            TaxonomyProposal(
                proposal_id=f"tax.{_proposal_slug(tier)}",
                tier=tier,
                count=count,
                novelty_type=novelty_type_for_tuple(tier, allow),
                evidence_ids=tuple(examples[tier]),
            )
        )
    return tuple(proposals)
