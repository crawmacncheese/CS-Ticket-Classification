"""Compile natural-language rule descriptions into validated RuleSpec JSON."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Any

from cs_tickets.classifier_rules import (
    RuleSpec,
    TierTuple,
    _rule_from_dict,
    rule_has_match_conditions,
    rule_spec_to_json,
)
from cs_tickets.rule_compile_corpus import INPUT_NORMALIZER_HINTS, SHIELD_WEIGHT_MIN
from cs_tickets.rule_compile_prompt import (
    build_compile_system_prompt,
    build_compile_user_context,
)
from cs_tickets.taxonomy import AllowList

_QUOTED_RE = re.compile(r'"([^"]+)"')
_MAP_TO_RE = re.compile(
    r"(?:update:\s*)?map\s+(.+?)\s+to\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)
_MARK_AS_RE = re.compile(
    r"\b(?:mark(?:\s+as)?|route\s+to|assign\s+to|categor(?:y|ize)(?:\s+as)?|classify\s+as)\s+(.+?)(?:\.|$)",
    re.IGNORECASE,
)
_CONTAINS_RE = re.compile(
    r"\b(?:contains|contain|includes|including|mentions|mentioned|has|have)\s+(.+?)(?:\s*,\s*|\s+mark\b|\s+then\b|\s+→|\.|$)",
    re.IGNORECASE,
)
_TIER_SHORTCUTS: dict[str, str] = {
    "junk": "junk",
    "spam": "junk",
    "system report": "system report",
    "sales lead": "sales leads",
    "sales leads": "sales leads",
    "renewal": "rate or renewal inquiry",
    "cancellation": "cancellation request",
    "refund": "refund request",
}


@dataclass(frozen=True)
class CompileResult:
    rule: RuleSpec | None
    rationale: str
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    raw: dict[str, Any] | None = None
    clarify_message: str | None = None
    attempts: int = 1


class CompileError(Exception):
    """User-facing compile failure."""


# Mechanical validation errors that warrant bounded LLM retry
_RETRYABLE_ERROR_MARKERS = (
    "not in allow-list",
    "match condition",
    "already exists",
    "missing 'rule'",
    "empty content",
    "no rule",
)


def _errors_are_retryable(errors: tuple[str, ...]) -> bool:
    if not errors:
        return False
    blob = " ".join(errors).lower()
    return any(m in blob for m in _RETRYABLE_ERROR_MARKERS)


def human_compile_clarify(errors: tuple[str, ...], *, message: str) -> str:
    """Analyst-facing clarify ask — no raw schema dumps."""
    joined = " ".join(errors).lower()
    if "allow-list" in joined or "tier" in joined:
        return (
            "I tried to draft a routing rule, but couldn't map it to a valid category path. "
            "Could you specify the target path (e.g. Billing & Admin > System Report) "
            "and whether this should stay a normal rule or a shield (always-win) rule?"
        )
    if "match condition" in joined:
        return (
            "I couldn't extract clear match signals (keywords / tags). "
            "Could you list the phrases that should trigger this rule "
            "(and any that should not)?"
        )
    if "already exists" in joined:
        return (
            "That rule id already exists in live config. "
            "Should I refine the existing rule instead, or use a new id?"
        )
    return (
        "I couldn't draft a valid rule from that request. "
        "Please clarify the target category, key match phrases, and whether this "
        "should beat shields like Stefan Rule. "
        f"(Original focus: {message[:120]})"
    )


def post_compile_warnings(
    rule: RuleSpec,
    live_rules: tuple[RuleSpec, ...],
) -> tuple[str, ...]:
    """C.3 — shield weight floors + soft semantic collision hints (non-blocking)."""
    warnings: list[str] = []
    if rule.override:
        floor = SHIELD_WEIGHT_MIN.get("junk", 16.0)
        if "stefan" in rule.id.lower() or "stefan" in (rule.display_name or "").lower():
            floor = SHIELD_WEIGHT_MIN.get("stefan", 18.0)
        if "live_chat" in rule.id.lower() or "chat" in rule.id.lower():
            floor = max(floor, SHIELD_WEIGHT_MIN.get("live_chat", 20.0))
        if rule.weight < floor:
            warnings.append(
                f"Shield weight {rule.weight} is below floor {floor} — raise weight or drop override."
            )
    # Semantic collision: same first blob token as an existing shield
    cand_blobs = {b.lower() for b in rule.any_blob[:3] if b}
    for live in live_rules:
        if not live.override:
            continue
        if live.id == rule.id:
            continue
        live_blobs = {b.lower() for b in live.any_blob[:5] if b}
        if cand_blobs and live_blobs.intersection(cand_blobs):
            warnings.append(
                f"May overlap live shield `{live.id}` (shared blob signals) — preview carefully."
            )
            break
        # same tier path + both override
        if rule.override and live.tier == rule.tier:
            warnings.append(
                f"Another shield `{live.id}` already targets the same path — check precedence."
            )
            break
    return tuple(warnings)

def normalize_user_message(text: str) -> str:
    lowered = text.strip().lower()
    for needle, _tag in INPUT_NORMALIZER_HINTS:
        if needle in lowered:
            return text.strip()
    return text.strip()


def _extract_quoted_phrases(text: str) -> tuple[str, ...]:
    return tuple(p.lower().strip() for p in _QUOTED_RE.findall(text) if p.strip())


def _extract_contains_phrase(text: str) -> str | None:
    match = _CONTAINS_RE.search(text)
    if not match:
        return None
    phrase = match.group(1).strip().strip('"').lower()
    phrase = re.sub(r"\s+", " ", phrase)
    if not phrase or len(phrase) > 80:
        return None
    return phrase


def _extract_mark_as_target(text: str) -> str | None:
    match = _MARK_AS_RE.search(text)
    if not match:
        return None
    target = match.group(1).strip().strip('"')
    return target or None


def _resolve_tier_shortcut(label: str, allow: AllowList) -> TierTuple | None:
    key = label.strip().lower()
    if key in _TIER_SHORTCUTS:
        key = _TIER_SHORTCUTS[key]
    return resolve_tier_from_text(key, allow)


def _slug_id(*parts: str) -> str:
    base = "_".join(re.sub(r"[^a-z0-9]+", "_", p.lower()).strip("_") for p in parts if p)
    base = base[:48] or "rule"
    return f"explicit.{base}"


def resolve_tier_from_text(text: str, allow: AllowList) -> TierTuple | None:
    """Map Gem-style path or tier4 label to a workbook 5-tuple."""
    if ">" in text:
        parts = [p.strip().lower() for p in text.split(">") if p.strip()]
    else:
        parts = [text.strip().lower()]
    candidates = list(allow.tuples)
    for part in parts:
        narrowed = [
            t
            for t in candidates
            if part in t[0].lower()
            or part in t[1].lower()
            or part in t[2].lower()
            or part in t[3].lower()
        ]
        if narrowed:
            candidates = narrowed
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        b2c = [t for t in candidates if t[0] == "B2C"]
        if len(b2c) == 1:
            return b2c[0]
        if len(b2c) > 1:
            # Prefer canonical Junk / System Report paths when many B2C siblings match.
            canonical = sorted({t for t in b2c})
            return canonical[0]
        return sorted(candidates)[0]
    if parts[-1] == "junk":
        junk = [t for t in allow.tuples if t[0] == "B2C" and t[1] == "Junk"]
        if junk:
            return sorted(junk)[0]
    for tup in allow.tuples:
        if parts[-1] in tup[3].lower():
            return tup
    return None


def _validate_compiled_rule(
    rule: RuleSpec,
    allow: AllowList,
    live_ids: frozenset[str],
    *,
    prior_rule_id: str | None = None,
) -> tuple[str, ...]:
    errors: list[str] = []
    if rule.tier not in allow.tuples:
        errors.append(f"Tier not in allow-list: {' / '.join(rule.tier[:4])}")
    if not rule_has_match_conditions(rule):
        errors.append("Rule needs at least one match condition (tags, subject, blob, requester, etc.).")
    if rule.id in live_ids and rule.id != prior_rule_id:
        errors.append(f"Rule id already exists: {rule.id}")
    return tuple(errors)


def _parse_llm_response(raw: dict[str, Any]) -> tuple[RuleSpec, str, tuple[str, ...]]:
    rule_raw = raw.get("rule")
    if not isinstance(rule_raw, dict):
        raise CompileError("Model response missing 'rule' object.")
    rule = _rule_from_dict(rule_raw)
    rationale = str(raw.get("rationale") or "Compiled rule.")
    warnings_raw = raw.get("warnings") or []
    warnings = tuple(str(w) for w in warnings_raw) if isinstance(warnings_raw, list) else ()
    return rule, rationale, warnings


def _call_gemini_json(
    system_prompt: str,
    user_text: str,
    *,
    model: str,
    api_key: str,
) -> dict[str, Any]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise CompileError(f"Gemini API error ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise CompileError(f"Gemini API unreachable: {exc}") from exc

    candidates = payload.get("candidates") or []
    if not candidates:
        raise CompileError("Gemini returned no candidates.")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    if not parts:
        raise CompileError("Gemini returned empty content.")
    text = parts[0].get("text") or ""
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise CompileError("Gemini JSON was not an object.")
    return parsed


def _call_openai_compatible_json(
    system_prompt: str,
    user_text: str,
    *,
    model: str,
    api_key: str,
    base_url: str,
    provider_label: str,
) -> dict[str, Any]:
    """OpenAI-style chat completions (DeepSeek, OpenAI, etc.)."""
    url = f"{base_url.rstrip('/')}/v1/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise CompileError(f"{provider_label} API error ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise CompileError(f"{provider_label} API unreachable: {exc}") from exc

    choices = payload.get("choices") or []
    if not choices:
        raise CompileError(f"{provider_label} returned no choices.")
    message = choices[0].get("message") or {}
    text = message.get("content") or ""
    if not text:
        raise CompileError(f"{provider_label} returned empty content.")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise CompileError(f"{provider_label} JSON was not an object.")
    return parsed


def _compile_llm_settings() -> tuple[str, str, str, str]:
    """Return (provider, api_key, model, api_base)."""
    provider = (os.environ.get("RULE_COMPILE_PROVIDER") or "gemini").strip().lower()
    api_key = (
        os.environ.get("RULE_COMPILE_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("QWEN_API_KEY_INTERNATIONAL")
        or os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or ""
    ).strip()
    default_models = {
        "deepseek": "deepseek-chat",
        "qwen": "qwen-plus",
        "dashscope": "qwen-plus",
        "gemini": "gemini-2.0-flash",
    }
    default_bases = {
        "deepseek": "https://api.deepseek.com",
        "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode",
        "dashscope": "https://dashscope-intl.aliyuncs.com/compatible-mode",
    }
    default_model = default_models.get(provider, "gemini-2.0-flash")
    model = (os.environ.get("RULE_COMPILE_MODEL") or default_model).strip()
    default_base = default_bases.get(provider, "")
    api_base = (os.environ.get("RULE_COMPILE_API_BASE") or default_base).strip()
    return provider, api_key, model, api_base


def compile_llm_configured() -> bool:
    _, api_key, _, _ = _compile_llm_settings()
    return bool(api_key)


def call_compile_llm_json(system_prompt: str, user_text: str) -> dict[str, Any]:
    provider, api_key, model, api_base = _compile_llm_settings()
    if not api_key:
        raise CompileError("RULE_COMPILE API key not configured.")
    return _call_compile_llm(
        system_prompt,
        user_text,
        provider=provider,
        model=model,
        api_key=api_key,
        api_base=api_base,
    )


def _call_compile_llm(
    system_prompt: str,
    user_text: str,
    *,
    provider: str,
    model: str,
    api_key: str,
    api_base: str,
) -> dict[str, Any]:
    if provider == "deepseek":
        return _call_openai_compatible_json(
            system_prompt,
            user_text,
            model=model,
            api_key=api_key,
            base_url=api_base or "https://api.deepseek.com",
            provider_label="DeepSeek",
        )
    if provider in ("qwen", "dashscope"):
        return _call_openai_compatible_json(
            system_prompt,
            user_text,
            model=model,
            api_key=api_key,
            base_url=api_base or "https://dashscope-intl.aliyuncs.com/compatible-mode",
            provider_label="Qwen (DashScope)",
        )
    if provider in ("openai", "openai_compatible"):
        return _call_openai_compatible_json(
            system_prompt,
            user_text,
            model=model,
            api_key=api_key,
            base_url=api_base or "https://api.openai.com",
            provider_label="OpenAI-compatible",
        )
    return _call_gemini_json(system_prompt, user_text, model=model, api_key=api_key)


def _heuristic_compile(
    message: str,
    allow: AllowList,
    *,
    prior_rule: RuleSpec | None = None,
) -> CompileResult:
    """Pattern-based compiler when LLM is unavailable (tests / no API key)."""
    text = message.strip()
    lowered = text.lower()
    warnings: list[str] = []
    phrases = _extract_quoted_phrases(text)

    tier: TierTuple | None = None
    map_match = _MAP_TO_RE.search(text)
    if map_match:
        tier = resolve_tier_from_text(map_match.group(2).strip(), allow)
    mark_target = _extract_mark_as_target(text)
    if tier is None and mark_target:
        tier = _resolve_tier_shortcut(mark_target, allow)
    if tier is None:
        for label in (
            "system report",
            "rate or renewal inquiry",
            "no content - live chat auto-trigger",
            "comments being block",
            "pr / external sales / editorial noise",
            "junk",
        ):
            if label in lowered or f"as {label}" in lowered or f"to {label}" in lowered:
                tier = _resolve_tier_shortcut(label, allow)
                if tier:
                    break

    override = any(
        kw in lowered
        for kw in ("critical:", "always", "every time", "even if refund", "stefan rule")
    )
    weight = 10.0
    is_junk_intent = "junk" in lowered and any(
        p in lowered for p in ("mark as", "route to", "classify as", "category")
    )
    if override or is_junk_intent and "junk" in lowered:
        if "conversation with" in lowered or "live chat" in lowered or "live-chat" in lowered:
            weight = SHIELD_WEIGHT_MIN["live_chat"]
            override = True
        elif "stefan" in lowered or "moderation" in lowered:
            weight = SHIELD_WEIGHT_MIN["stefan"]
            override = True
        elif "junk" in lowered:
            weight = max(weight, SHIELD_WEIGHT_MIN["junk"])
        elif override:
            weight = SHIELD_WEIGHT_MIN["default_max"]

    any_blob: tuple[str, ...] = ()
    any_subject: tuple[str, ...] = ()
    exclude_blob: tuple[str, ...] = ()
    any_requester_domain: tuple[str, ...] = ()
    display_name = ""

    contains_phrase = _extract_contains_phrase(text)
    if phrases:
        any_blob = phrases
    elif contains_phrase:
        any_blob = (contains_phrase,)
        if "rosetta" in lowered:
            tier = tier or _resolve_tier_shortcut("system report", allow)
            if "not cancellation" in lowered or "not cancel" in lowered:
                exclude_blob = ("cancellation request", "cancel my")
    elif "rosetta" in lowered:
        any_blob = ("rosetta system email",)
        tier = tier or resolve_tier_from_text("system report", allow)
        if "not cancellation" in lowered or "not cancel" in lowered:
            exclude_blob = ("cancellation request", "cancel my")
    elif "stripe payment completed" in lowered:
        any_blob = ("stripe payment completed",)
    elif "privaterelay.appleid.com" in lowered:
        any_requester_domain = ("privaterelay.appleid.com",)
    elif "conversation with" in lowered:
        any_subject = ("conversation with",)
        if "subscribe" in lowered or "url" in lowered:
            any_blob = ("subscribe.scmp.com",)

    if "stefan" in lowered:
        display_name = "Stefan Rule"
        any_blob = any_blob or ("deleted comment", "moderation", "biased moderator")
        tier = tier or resolve_tier_from_text("comments being block", allow)

    if "not " in lowered and "cancellation" in lowered and not exclude_blob:
        exclude_blob = ("cancellation", "cancel my subscription")

    if prior_rule is not None:
        tier = tier or prior_rule.tier
        weight = weight if weight != 10.0 else prior_rule.weight
        override = override or prior_rule.override
        any_blob = any_blob or prior_rule.any_blob
        any_subject = any_subject or prior_rule.any_subject
        exclude_blob = exclude_blob or prior_rule.exclude_blob
        any_requester_domain = any_requester_domain or prior_rule.any_requester_domain
        display_name = display_name or prior_rule.display_name

    if tier is None:
        return CompileResult(
            rule=None,
            rationale="Could not resolve target category from message.",
            warnings=tuple(warnings),
            errors=("Could not map message to an allow-list tier. Name the category path.",),
        )

    rule_id = prior_rule.id if prior_rule else _slug_id(
        tier[3],
        phrases[0] if phrases else (contains_phrase or "rule"),
    )
    rule = RuleSpec(
        id=rule_id,
        tier=tier,
        weight=weight,
        any_blob=any_blob,
        any_subject=any_subject,
        exclude_blob=exclude_blob,
        any_requester_domain=any_requester_domain,
        override=override,
        display_name=display_name,
        source="explicit_rule",
        source_message=text[:500],
    )
    warnings.append("Compiled with heuristic fallback (no LLM API key).")
    return CompileResult(
        rule=rule,
        rationale=f"Route tickets matching your description to {' > '.join(tier[:4])}.",
        warnings=tuple(warnings),
        errors=(),
        raw={"heuristic": True},
    )


def compile_rule_message(
    message: str,
    *,
    allow: AllowList,
    live_rules: tuple[RuleSpec, ...],
    prior_rule: RuleSpec | None = None,
    exemplar_row: dict[str, Any] | None = None,
    explain_payload: dict[str, Any] | None = None,
    max_retries: int = 2,
) -> CompileResult:
    """Compile one user message into a RuleSpec.

    On mechanical validation failures, retry the LLM up to ``max_retries`` times
    with the error text appended. Exhausted retries return ``clarify_message``
    for analysts (no raw schema dump required in UI).
    """
    normalized = normalize_user_message(message)
    if not normalized:
        return CompileResult(
            rule=None,
            rationale="",
            warnings=(),
            errors=("Message is empty.",),
            clarify_message="Please describe the routing rule you want to draft.",
        )

    live_ids = frozenset(r.id for r in live_rules)
    context = build_compile_user_context(
        exemplar_row=exemplar_row,
        explain_payload=explain_payload,
        prior_rule=prior_rule,
    )
    base_user = normalized
    if context:
        base_user = f"{context}\n\nUser message:\n{normalized}"

    provider, api_key, model, api_base = _compile_llm_settings()
    attempts = 0
    last_errors: tuple[str, ...] = ()
    last_rationale = ""
    last_warnings: tuple[str, ...] = ()
    last_raw: dict[str, Any] | None = None
    retry_hints = ""

    while attempts <= max_retries:
        attempts += 1
        user_blob = base_user
        if retry_hints:
            user_blob = (
                f"{base_user}\n\nPrevious compile failed validation. Fix these issues "
                f"and return valid RuleSpec JSON only:\n{retry_hints}"
            )

        raw: dict[str, Any] | None = None
        rationale = ""
        warnings: tuple[str, ...] = ()
        rule: RuleSpec | None = None

        if api_key:
            system = build_compile_system_prompt(
                allow,
                live_rules,
                user_message=normalized,
            )
            try:
                raw = _call_compile_llm(
                    system,
                    user_blob,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    api_base=api_base,
                )
                rule, rationale, warnings = _parse_llm_response(raw)
            except (CompileError, json.JSONDecodeError, ValueError, KeyError) as exc:
                last_errors = (str(exc),)
                last_rationale = str(exc)
                last_raw = raw
                if attempts <= max_retries and _errors_are_retryable(last_errors):
                    retry_hints = str(exc)
                    continue
                clarify = human_compile_clarify(last_errors, message=normalized)
                return CompileResult(
                    rule=None,
                    rationale=str(exc),
                    warnings=(),
                    errors=last_errors,
                    raw=raw,
                    clarify_message=clarify,
                    attempts=attempts,
                )
        else:
            heuristic = _heuristic_compile(normalized, allow, prior_rule=prior_rule)
            if heuristic.errors:
                return CompileResult(
                    rule=None,
                    rationale=heuristic.rationale,
                    warnings=heuristic.warnings,
                    errors=heuristic.errors,
                    raw=heuristic.raw,
                    clarify_message=human_compile_clarify(
                        heuristic.errors, message=normalized
                    ),
                    attempts=attempts,
                )
            rule = heuristic.rule
            rationale = heuristic.rationale
            warnings = heuristic.warnings
            raw = heuristic.raw

        if rule is None:
            last_errors = ("Compile produced no rule.",)
            last_rationale = rationale
            last_warnings = warnings
            last_raw = raw
            if attempts <= max_retries:
                retry_hints = "Compile produced no rule object."
                continue
            break

        if not rule.source_message:
            rule = replace(
                rule,
                source_message=normalized[:500],
                source=rule.source or "explicit_rule",
            )

        errors = _validate_compiled_rule(
            rule,
            allow,
            live_ids,
            prior_rule_id=prior_rule.id if prior_rule else None,
        )
        if errors:
            last_errors = errors
            last_rationale = rationale
            last_warnings = warnings
            last_raw = raw
            if attempts <= max_retries and _errors_are_retryable(errors):
                retry_hints = "; ".join(errors)
                continue
            return CompileResult(
                rule=None,
                rationale=rationale,
                warnings=warnings,
                errors=errors,
                raw=raw,
                clarify_message=human_compile_clarify(errors, message=normalized),
                attempts=attempts,
            )

        extra = post_compile_warnings(rule, live_rules)
        warnings = warnings + extra
        if rule.override and rule.weight < SHIELD_WEIGHT_MIN["junk"]:
            rule = replace(rule, weight=SHIELD_WEIGHT_MIN["junk"])
            warnings = warnings + ("Raised weight for override rule.",)

        return CompileResult(
            rule=rule,
            rationale=rationale,
            warnings=warnings,
            errors=(),
            raw=raw,
            attempts=attempts,
        )

    clarify = human_compile_clarify(last_errors, message=normalized)
    return CompileResult(
        rule=None,
        rationale=last_rationale,
        warnings=last_warnings,
        errors=last_errors or ("Compile failed.",),
        raw=last_raw,
        clarify_message=clarify,
        attempts=attempts,
    )


def compile_result_to_api_dict(result: CompileResult) -> dict[str, Any]:
    from cs_tickets.consistency_gateway import attach_compile_risk

    if result.errors:
        payload = {
            "ok": False,
            "errors": list(result.errors),
            "rationale": result.rationale,
            "warnings": list(result.warnings),
            "attempts": result.attempts,
        }
        if result.clarify_message:
            payload["clarify_message"] = result.clarify_message
        return attach_compile_risk(payload)
    assert result.rule is not None
    return attach_compile_risk(
        {
            "ok": True,
            "rule": rule_spec_to_json(result.rule),
            "rationale": result.rationale,
            "warnings": list(result.warnings),
            "attempts": result.attempts,
        }
    )
