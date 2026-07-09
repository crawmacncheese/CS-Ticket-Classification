"""Tests for allow-list rejection diagnosis (TBC category suggestion)."""

from __future__ import annotations

from cs_tickets.category_suggest import _parse_suggest_response
from cs_tickets.taxonomy import AllowList, classify_allowlist_rejection, load_allowlist


def test_classify_hallucinated_tier(repo_root) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        import pytest

        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    candidate = ("FakeSegment", "FakeStream", "FakeCat", "FakeType", "N/A")
    rejection = classify_allowlist_rejection(candidate, allow, tax)
    assert rejection.cause == "hallucinated"
    assert not rejection.can_add_to_allowlist
    assert "not in the taxonomy" in rejection.message


def test_classify_typo_close_match(repo_root) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        import pytest

        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    existing = next(t for t in sorted(allow.tuples) if t[3])
    typo = (existing[0], existing[1], existing[2], existing[3] + "x", existing[4])
    rejection = classify_allowlist_rejection(typo, allow, tax)
    assert rejection.cause == "typo_close_match"
    assert rejection.close_match_tier is not None
    assert rejection.close_match_tier[:3] == typo[:3]
    assert not rejection.can_add_to_allowlist


def test_classify_granular_new_can_add(repo_root) -> None:
    tax = repo_root / "doc" / "Taxonomy.csv"
    xlsx = repo_root / "doc" / "CS_ticket_new_categorizations.xlsx"
    if not tax.is_file() or not xlsx.is_file():
        import pytest

        pytest.skip("doc artifacts missing")
    allow = load_allowlist(tax, xlsx)
    base = next(t for t in sorted(allow.tuples) if t[4] == "N/A")
    novel_granular = (base[0], base[1], base[2], base[3], "ProbeGranularUI")
    if novel_granular in allow.tuples:
        import pytest

        pytest.skip("fixture already contains probe granular")
    rejection = classify_allowlist_rejection(novel_granular, allow, tax)
    assert rejection.cause == "taxonomy_not_allowlisted"
    assert rejection.can_add_to_allowlist
    assert rejection.novelty_type == "granular_new"


def test_parse_suggest_response_surfaces_rejection() -> None:
    allow = AllowList(
        tuples=frozenset(
            {
                ("B2C", "Service Task", "General Support", "Account", "N/A"),
            }
        )
    )
    raw = {
        "tier": ["B2C", "Service Task", "General Support", "Account", "Stripe"],
        "rationale": "billing",
        "confidence": "high",
    }
    tier, _rationale, _confidence, errors, rejection, _tbc = _parse_suggest_response(raw, allow)
    assert tier is None
    assert errors
    assert rejection is not None
    assert rejection.cause == "taxonomy_not_allowlisted"
    assert rejection.can_add_to_allowlist
