"""Parse docs/taxonomy-requirements.md for compile-time injection (Phase C.1)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cs_tickets.classifier_rules import RuleSpec
from cs_tickets.repo_paths import resolve_repo_root

_PROTOCOL_RE = re.compile(r"\*\*protocol_version:\*\*\s*(\d+)", re.IGNORECASE)
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SWEEP_ID_RE = re.compile(r"\*\*sweep_id:\*\*\s*`?([a-z0-9_]+)`?", re.IGNORECASE)
_SWEEP_IDS_RE = re.compile(r"\*\*sweep_ids:\*\*\s*(.+)", re.IGNORECASE)
_COMPILE_PHRASE_RE = re.compile(r"\*\*compile_phrase:\*\*\s*(.+)", re.IGNORECASE)
_BACKTICK_ID_RE = re.compile(r"`([a-z0-9_]+)`")


@dataclass(frozen=True)
class TaxonomySection:
    title: str
    body: str
    sweep_ids: tuple[str, ...] = ()
    compile_phrases: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "sweep_ids": list(self.sweep_ids),
            "compile_phrases": list(self.compile_phrases),
        }


@dataclass(frozen=True)
class TaxonomyRequirements:
    protocol_version: int
    global_precedence: str
    sections: tuple[TaxonomySection, ...] = ()
    source_path: str = ""

    def sections_for_scope(
        self,
        *,
        categories: tuple[str, ...] = (),
        sweep_ids: tuple[str, ...] = (),
        text_hints: str = "",
        limit: int = 4,
    ) -> tuple[TaxonomySection, ...]:
        """Pick scoped sections by category title, sweep id, or text overlap."""
        cats = {c.lower().strip() for c in categories if c.strip()}
        sweeps = {s.lower().strip() for s in sweep_ids if s.strip()}
        hint = (text_hints or "").lower()
        scored: list[tuple[int, TaxonomySection]] = []
        for sec in self.sections:
            title_l = sec.title.lower()
            score = 0
            if cats and any(c in title_l for c in cats):
                score += 3
            sec_sweeps = {s.lower() for s in sec.sweep_ids}
            if sweeps and sec_sweeps.intersection(sweeps):
                score += 4
            if hint:
                if any(c in hint for c in cats) and any(c in title_l for c in cats):
                    score += 1
                for sw in sec.sweep_ids:
                    if sw.lower() in hint:
                        score += 2
                # keyword overlap with title tokens
                for token in re.findall(r"[a-z0-9]{4,}", title_l):
                    if token in hint:
                        score += 1
            if score > 0:
                scored.append((score, sec))
        scored.sort(key=lambda x: (-x[0], x[1].title))
        return tuple(s for _, s in scored[:limit])


def default_taxonomy_path(repo_root: Path | None = None) -> Path:
    root = repo_root or resolve_repo_root()
    return root / "docs" / "taxonomy-requirements.md"


def _section_sweep_ids(body: str) -> tuple[str, ...]:
    found: list[str] = []
    m = _SWEEP_ID_RE.search(body)
    if m:
        found.append(m.group(1))
    m2 = _SWEEP_IDS_RE.search(body)
    if m2:
        found.extend(_BACKTICK_ID_RE.findall(m2.group(1)))
    # also bare list like: `a`, `b`
    for sid in _BACKTICK_ID_RE.findall(body):
        if sid not in found and ("sweep" in body.lower() or sid in body):
            # keep only ids appearing near sweep_ids line — already handled; skip noise
            pass
    # Deduplicate preserving order
    out: list[str] = []
    seen: set[str] = set()
    for s in found:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return tuple(out)


def _section_compile_phrases(body: str) -> tuple[str, ...]:
    return tuple(m.group(1).strip() for m in _COMPILE_PHRASE_RE.finditer(body) if m.group(1).strip())


def parse_taxonomy_requirements(text: str, *, source_path: str = "") -> TaxonomyRequirements:
    version = 1
    m = _PROTOCOL_RE.search(text)
    if m:
        version = int(m.group(1))

    headings = list(_HEADING_RE.finditer(text))
    sections: list[TaxonomySection] = []
    global_precedence = ""

    for i, match in enumerate(headings):
        title = match.group(1).strip()
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[start:end].strip()
        if title.lower().startswith("global precedence"):
            global_precedence = body
            continue
        if title.lower() in {"how to use this file", "core categories"}:
            continue
        if title.lower().startswith("field glossary"):
            continue
        sections.append(
            TaxonomySection(
                title=title,
                body=body,
                sweep_ids=_section_sweep_ids(body),
                compile_phrases=_section_compile_phrases(body),
            )
        )

    return TaxonomyRequirements(
        protocol_version=version,
        global_precedence=global_precedence.strip(),
        sections=tuple(sections),
        source_path=source_path,
    )


def load_taxonomy_requirements(path: Path | None = None) -> TaxonomyRequirements:
    p = path or default_taxonomy_path()
    return parse_taxonomy_requirements(p.read_text(encoding="utf-8"), source_path=str(p))


def shield_weight_table(live_rules: tuple[RuleSpec, ...], *, limit: int = 24) -> str:
    """Compact live shield (override) table for compile prompt."""
    shields = [r for r in live_rules if r.override][:limit]
    lines = [
        "## Live shields (override — weight floors)",
        "",
        "| rule_id | weight | path |",
        "|---------|--------|------|",
    ]
    if not shields:
        lines.append("| (none in live rules) | — | — |")
        return "\n".join(lines)
    for r in shields:
        path = " > ".join(r.tier[:4])
        lines.append(f"| `{r.id}` | {r.weight} | {path} |")
    return "\n".join(lines)


def format_taxonomy_for_compile(
    tax: TaxonomyRequirements,
    *,
    scoped: tuple[TaxonomySection, ...],
    live_rules: tuple[RuleSpec, ...],
    max_chars: int = 4500,
) -> str:
    """Global precedence + scoped excerpts + shield table, token-capped."""
    parts: list[str] = [
        f"## Taxonomy protocol (v{tax.protocol_version})",
        "",
        "### Global precedence",
        tax.global_precedence or "(missing)",
        "",
        shield_weight_table(live_rules),
    ]
    if scoped:
        parts.append("")
        parts.append("### Scoped taxonomy excerpts")
        for sec in scoped:
            parts.append(f"#### {sec.title}")
            # Prefer compact body — trim if huge
            body = sec.body
            if len(body) > 900:
                body = body[:880] + "\n…"
            parts.append(body)
            parts.append("")
    text = "\n".join(parts).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n… (truncated)"
    return text


def infer_scope_from_message(message: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Best-effort categories + sweep_ids from user compile phrasing."""
    lowered = message.lower()
    cats: list[str] = []
    for label in (
        "cancellation",
        "refund",
        "system report",
        "invoice",
        "delete account",
        "gdpr",
        "live chat",
        "junk",
    ):
        if label in lowered:
            cats.append(label)
    sweeps: list[str] = []
    for sid in (
        "rosetta_footer",
        "rosetta_system_email",
        "esp_print",
        "posties_young_post",
        "refund_precedence",
        "account_deletion",
        "invoice_request",
    ):
        key = sid.replace("_", " ")
        if sid in lowered or key in lowered or ("rosetta" in lowered and "rosetta" in sid):
            sweeps.append(sid if sid != "rosetta_system_email" else "rosetta_footer")
    # dedupe
    def uniq(items: list[str]) -> tuple[str, ...]:
        seen: set[str] = set()
        out: list[str] = []
        for i in items:
            if i not in seen:
                seen.add(i)
                out.append(i)
        return tuple(out)

    return uniq(cats), uniq(sweeps)
