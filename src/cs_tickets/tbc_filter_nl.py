"""Natural-language review focus + batch rule prefill for TBC queue."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from cs_tickets.rule_compile import CompileError, call_compile_llm_json, compile_llm_configured
from cs_tickets.taxonomy import AllowList

from cs_tickets.tbc_queue_filters import TbcQueueFilter

_SEGMENT_RE = re.compile(r"\b(B2C|B2B)\b", re.IGNORECASE)
_CONTAINS_RE = re.compile(
    r"(?:anything\s+)?(?:contains?|containing|with|mentioning|mentions?|from)\s+[\"']?([a-z0-9@._-]{2,40})",
    re.IGNORECASE,
)
_CONTAINS_LIST_TOKEN = re.compile(r"[a-z0-9@._-]{2,40}", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9@._-]+", re.IGNORECASE)

_CONTAINS_KEYWORD_START_RE = re.compile(
    r"(?:anything\s+)?(?:contains?|containing|with|mentioning|mentions?|from)\s+[\"']?([a-z0-9@._-]{2,40})",
    re.IGNORECASE,
)


def _extract_contains_keywords_or_list(raw: str, *, move_start: int | None, review_start: int | None) -> list[str]:
    """Extract keyword lists like 'contains a or b' => ['a','b'].

    Returns [] when it can't confidently parse an OR/AND list.
    """
    start = _CONTAINS_KEYWORD_START_RE.search(raw)
    if not start:
        return []

    # Limit the substring so we don't accidentally capture tokens from later clauses.
    end = len(raw)
    if move_start is not None:
        end = min(end, move_start)
    if review_start is not None:
        end = min(end, review_start)

    first = start.group(1)
    rest = raw[start.end() : end]

    # Capture tokens following explicit boolean operators.
    tokens = [first]
    or_tokens = re.findall(
        r"(?:\bor\b|\band\b)\s*[\"']?([a-z0-9@._-]{2,40})",
        rest,
        flags=re.IGNORECASE,
    )
    if not or_tokens:
        return []

    tokens.extend(or_tokens)
    # Dedupe preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        t2 = str(t).strip().lower()
        if t2 and t2 not in seen:
            seen.add(t2)
            out.append(t2)
    return out
_MOVE_TO_RE = re.compile(
    r"(?:move|route|map|assign)(?:\s+\w+){0,6}?\s+(?:to|under)\s+[\"']?([^\"'.,\n]+)",
    re.IGNORECASE,
)
_REVIEW_CATEGORIES_RE = re.compile(
    r"(?:review|focus on|look at)\s+(?:these\s+)?(?:categories?\s+)?(?:under\s+\w+\s*)?"
    r"(?:[:.]?\s*)?(.+)$",
    re.IGNORECASE,
)
_NUMBERED_ITEM_RE = re.compile(r"\d+[.)]\s*([^,\d]+?)(?=\s*\d+[.)]|$)", re.IGNORECASE)


@dataclass(frozen=True)
class ReviewFocusParseResult:
    ok: bool
    filter: TbcQueueFilter
    rule_target: str
    rationale: str
    source: str  # deterministic | llm | none
    errors: tuple[str, ...] = ()


def _clean_category_token(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" .,;"))


def _split_category_phrases(blob: str) -> list[str]:
    blob = blob.strip()
    if not blob:
        return []
    numbered = _NUMBERED_ITEM_RE.findall(blob)
    if numbered:
        return [_clean_category_token(x) for x in numbered if _clean_category_token(x)]
    parts = re.split(r"\s*(?:,| and | & )\s*", blob, flags=re.IGNORECASE)
    return [_clean_category_token(p) for p in parts if _clean_category_token(p)]


def _known_category_tokens(allow: AllowList) -> set[str]:
    tokens: set[str] = set()
    for tup in allow.tuples:
        for part in tup[:4]:
            p = str(part).strip()
            if p and "tbc" not in p.lower():
                tokens.add(p)
    return tokens


def _match_categories_from_text(text: str, allow: AllowList) -> list[str]:
    lowered = text.lower()
    hits: list[str] = []
    known = _known_category_tokens(allow)
    # Prefer longer labels first (e.g. "Access Loop or App Bug" before "Access")
    for label in sorted(known, key=len, reverse=True):
        if len(label) < 4:
            continue
        if label.lower() in lowered and label not in hits:
            hits.append(label)
    if hits:
        return hits[:6]

    # Fallback: allow partial word matches against known labels.
    # This covers common analyst shorthand like "cancellation" matching
    # an allow-list label like "Cancellation Request".
    words = [w.lower() for w in _WORD_RE.findall(lowered) if len(w) >= 5]
    if not words:
        return []
    for label in sorted(known, key=len, reverse=True):
        l = label.lower()
        if len(l) < 4:
            continue
        if any(w in l and w in lowered for w in words) and label not in hits:
            hits.append(label)
        if len(hits) >= 6:
            break
    return hits[:6]


def parse_review_focus_deterministic(text: str, allow: AllowList) -> ReviewFocusParseResult:
    """Heuristic Christine-style focus phrases without LLM."""
    raw = text.strip()
    if not raw:
        return ReviewFocusParseResult(
            ok=False,
            filter=TbcQueueFilter(),
            rule_target="",
            rationale="",
            source="none",
            errors=("Enter a review focus, e.g. review B2C cancellation or contains sherina.",),
        )

    q = ""
    tier1 = ""
    categories: list[str] = []
    rule_target = ""

    seg = _SEGMENT_RE.search(raw)
    if seg:
        tier1 = seg.group(1).upper()

    move = _MOVE_TO_RE.search(raw)
    review = _REVIEW_CATEGORIES_RE.search(raw)
    move_start = move.start() if move else None
    # IMPORTANT: _REVIEW_CATEGORIES_RE matches from the leading "review".
    # If we used review.start() to bound keyword extraction, we'd truncate the
    # whole string and break parsing patterns like:
    #   "review B2C tickets containing postie or scmp"
    review_start = None

    # Prefer parsing explicit keyword lists like "contains postie or scmp"
    # into an OR list encoded as q="postie|scmp".
    kw_list = _extract_contains_keywords_or_list(
        raw,
        move_start=move_start,
        review_start=review_start,
    )
    if kw_list and len(kw_list) > 1:
        q = "|".join(kw_list)
    else:
        contains = _CONTAINS_RE.search(raw)
        if contains:
            q = contains.group(1).strip()

    if move:
        rule_target = _clean_category_token(move.group(1))
        if rule_target and rule_target.lower() not in {c.lower() for c in categories}:
            categories.append(rule_target)

    explicit_categories = False
    if review:
        tail = (review.group(1) or "").strip()
        # "review (B2C) tickets containing scmp" should be interpreted as a keyword search,
        # not a category label like "tickets containing scmp".
        if re.search(r"\btickets?\b", tail, flags=re.IGNORECASE) and (
            _CONTAINS_RE.search(tail)
            or re.search(r"\bcontain(?:s|ing)?\b", tail, flags=re.IGNORECASE)
            or re.search(r"\bwith\b", tail, flags=re.IGNORECASE)
        ):
            parsed = []
        else:
            parsed = _split_category_phrases(tail)
        if parsed:
            explicit_categories = True
            categories.extend(parsed)

    # Only fall back to fuzzy allow-list token matching when the analyst did not
    # explicitly enumerate categories (e.g. "1. Cancellation 2. Refund ...").
    # Otherwise we risk adding generic fragments like "Access"/"Loop" that make
    # the slice overly restrictive in the portal.
    if not explicit_categories:
        categories.extend(_match_categories_from_text(raw, allow))

    # Dedupe categories preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for cat in categories:
        key = cat.lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(cat)
    categories = deduped

    filt = TbcQueueFilter(q=q, tier1=tier1, categories=tuple(categories))
    if not filt.active and not rule_target:
        return ReviewFocusParseResult(
            ok=False,
            filter=filt,
            rule_target="",
            rationale="",
            source="deterministic",
            errors=("Could not parse focus — try keywords like B2C, cancellation, or contains sherina.",),
        )

    parts: list[str] = []
    if q:
        parts.append(f'contains "{q}"')
    if tier1:
        parts.append(tier1)
    if categories:
        parts.append("categories: " + ", ".join(categories))
    rationale = "Parsed focus: " + "; ".join(parts) if parts else f"Rule target: {rule_target}"

    return ReviewFocusParseResult(
        ok=True,
        filter=filt,
        rule_target=rule_target,
        rationale=rationale,
        source="deterministic",
    )


def _parse_llm_focus_response(raw: dict[str, Any]) -> tuple[TbcQueueFilter, str, str]:
    q = str(raw.get("q") or "").strip()
    tier1 = str(raw.get("tier1") or "").strip().upper()
    if tier1 not in ("B2C", "B2B"):
        tier1 = ""
    cats_raw = raw.get("categories") or []
    categories: list[str] = []
    if isinstance(cats_raw, list):
        categories = [str(c).strip() for c in cats_raw if str(c).strip()]
    elif isinstance(cats_raw, str) and cats_raw.strip():
        categories = _split_category_phrases(cats_raw)
    rule_target = str(raw.get("rule_target") or raw.get("target_category") or "").strip()
    rationale = str(raw.get("rationale") or "AI-parsed review focus.").strip()
    return TbcQueueFilter(q=q, tier1=tier1, categories=tuple(categories)), rule_target, rationale


def parse_review_focus_nl(
    text: str,
    allow: AllowList,
    *,
    use_llm: bool = True,
) -> ReviewFocusParseResult:
    """Parse natural-language review focus; LLM when configured, else heuristics."""
    det = parse_review_focus_deterministic(text, allow)
    if det.ok or not use_llm or not compile_llm_configured():
        return det

    system = "\n".join(
        [
            "You parse analyst review focus for a manual-review (TBC) ticket queue.",
            "Output ONLY JSON:",
            '{"q": "", "tier1": "B2C|B2B|", "categories": ["..."], '
            '"rule_target": "optional category path for a routing rule", "rationale": "..."}',
            "Rules:",
            "- q: keyword to search subject/body/tags (e.g. sherina, stripe). Empty if none.",
            "- tier1: B2C or B2B when segment is mentioned.",
            "- categories: substring labels to match tier paths (e.g. Print, Cancellation, Access Loop).",
            "- rule_target: when user wants to MOVE/ROUTE tickets to a category (e.g. under Print).",
            "- Do NOT invent tier paths outside common CS taxonomy labels.",
        ]
    )
    user = f"Parse this review focus:\n{text.strip()}"
    try:
        raw = call_compile_llm_json(system, user)
        filt, rule_target, rationale = _parse_llm_focus_response(raw)
        if not filt.active and not rule_target:
            return ReviewFocusParseResult(
                ok=False,
                filter=filt,
                rule_target=rule_target,
                rationale=rationale,
                source="llm",
                errors=("AI could not extract a filter from that focus.",),
            )
        return ReviewFocusParseResult(
            ok=True,
            filter=filt,
            rule_target=rule_target,
            rationale=rationale,
            source="llm",
        )
    except (CompileError, json.JSONDecodeError, ValueError, KeyError) as exc:
        return ReviewFocusParseResult(
            ok=False,
            filter=det.filter,
            rule_target=det.rule_target,
            rationale="",
            source="llm",
            errors=(str(exc),),
        )


def build_filter_batch_rule_prefill(
    filt: TbcQueueFilter,
    *,
    matched_count: int,
    sample_ticket_ids: tuple[str, ...],
    sample_quotes: tuple[str, ...],
    rule_target: str = "",
) -> str:
    """Christine-style batch rule seed for the active review focus."""
    focus_parts: list[str] = []
    if filt.q:
        focus_parts.append(f'containing "{filt.q}"')
    if filt.tier1:
        focus_parts.append(f"{filt.tier1} segment")
    if filt.categories:
        focus_parts.append("category focus: " + ", ".join(filt.categories))
    focus = " and ".join(focus_parts) or "matching the current review focus"

    examples: list[str] = []
    for tid, quote in zip(sample_ticket_ids, sample_quotes, strict=False):
        examples.append(f"#{tid} — {quote[:120]}")
    example_block = "\n".join(f"- {line}" for line in examples[:3])

    target = (rule_target or "").strip()
    if not target and filt.categories:
        target = filt.categories[0]
    target_line = (
        f'Update: Map tickets {focus} to {target}.'
        if target
        else f"Update: Map tickets {focus} to [target category from allow-list]."
    )

    lines = [
        target_line,
        "",
        f"Review focus batch: {matched_count} manual-review ticket"
        f"{'s' if matched_count != 1 else ''} in this filter.",
    ]
    if example_block:
        lines.extend(["", "Example tickets:", example_block])
    if filt.q:
        lines.extend(
            [
                "",
                f'Use any_blob or subject match for "{filt.q}" (validate against exemplar tickets).',
            ]
        )
    return "\n".join(lines).strip()


def review_focus_to_api_dict(result: ReviewFocusParseResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "filter": result.filter.as_dict(),
        "rule_target": result.rule_target,
        "rationale": result.rationale,
        "source": result.source,
        "errors": list(result.errors),
    }
