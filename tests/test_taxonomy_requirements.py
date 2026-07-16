"""Tests for taxonomy-requirements.md parse + compile inject helpers."""

from __future__ import annotations

from pathlib import Path

from cs_tickets.classifier_rules import RuleSpec
from cs_tickets.taxonomy_requirements import (
    format_taxonomy_for_compile,
    infer_scope_from_message,
    load_taxonomy_requirements,
    parse_taxonomy_requirements,
    shield_weight_table,
)


def test_parse_live_taxonomy_file(repo_root: Path) -> None:
    tax = load_taxonomy_requirements(repo_root / "docs" / "taxonomy-requirements.md")
    assert tax.protocol_version >= 1
    assert "stefan" in tax.global_precedence.lower()
    all_sweeps = {sid for sec in tax.sections for sid in sec.sweep_ids}
    assert "rosetta_footer" in all_sweeps


def test_sections_for_scope_rosetta() -> None:
    sample = """
**protocol_version:** 1

## Global precedence (shields)

1. Stefan Rule first.

## Cross-cutting routing rules

### Rosetta System Email footer

- **sweep_id:** `rosetta_footer`
- **compile_phrase:** Map Rosetta to System Report.
"""
    tax = parse_taxonomy_requirements(sample)
    scoped = tax.sections_for_scope(sweep_ids=("rosetta_footer",), text_hints="rosetta")
    assert scoped
    assert "rosetta_footer" in scoped[0].sweep_ids
    assert scoped[0].compile_phrases


def test_format_includes_global_and_shields() -> None:
    tax = parse_taxonomy_requirements(
        "**protocol_version:** 2\n\n## Global precedence\n\nShields first.\n\n## Rosetta\n\n"
        "- **sweep_id:** `rosetta_footer`\n"
    )
    rule = RuleSpec(
        id="stefan.rule",
        tier=("B2C", "Account Management", "Comments", "Comments being block", "N/A"),
        weight=18.0,
        override=True,
        any_blob=("moderator",),
    )
    text = format_taxonomy_for_compile(
        tax,
        scoped=tax.sections_for_scope(sweep_ids=("rosetta_footer",)),
        live_rules=(rule,),
    )
    assert "protocol (v2)" in text
    assert "Shields first" in text
    assert "stefan.rule" in text
    assert "Live shields" in text


def test_shield_weight_table_empty() -> None:
    assert "(none in live rules)" in shield_weight_table(())


def test_infer_scope_from_message_rosetta() -> None:
    cats, sweeps = infer_scope_from_message(
        'If it contains "Thanks. Rosetta System Email", map to System Report'
    )
    assert "system report" in cats or sweeps
    assert "rosetta_footer" in sweeps
