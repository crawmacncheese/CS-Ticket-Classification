from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleProposal:
    proposal_id: str
    kind: str
    tier: tuple[str, str, str, str, str]
    weight: float
    support: int
    purity: float
    any_tags: tuple[str, ...] = ()
    all_tags: tuple[str, ...] = ()
    any_subject: tuple[str, ...] = ()
    any_blob: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    conflict: str | None = None


@dataclass(frozen=True)
class TaxonomyProposal:
    proposal_id: str
    tier: tuple[str, str, str, str, str]
    count: int
    novelty_type: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MineConfig:
    min_support: int = 5
    min_purity: float = 0.85
    tag_any_purity: float = 0.90
    max_evidence: int = 5
    exclude_tbc: bool = True
    skip_already_classified: bool = True
