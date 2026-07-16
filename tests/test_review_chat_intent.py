"""Mirror Review-chat intent heuristics (keep in sync with static/rules.js).

Layer A (client): compile + clear focus + TBC queue handoff.
Layer B (server): everything else is focus-parse; clarify is a server outcome.
"""

from __future__ import annotations

import re


def looks_like_compile(text: str) -> bool:
    t = text.lower()
    return bool(
        re.search(r"\bmap\b", t)
        or re.search(r"\bmark\s+as\b", t)
        or re.search(r"\broute\s+to\b", t)
        or re.search(r"\bupdate:\s*", t)
        or re.search(r"\bcompile\b", t)
        or re.search(r"\bdraft\s+(a\s+)?rule\b", t)
        or re.search(r"\bpropose\s+(a\s+)?rule\b", t)
        or re.search(r"\bnot\s+cancellation\b", t)
        or ('"' in t and re.search(r"\bto\b", t))
    )


def looks_like_tbc_handoff(text: str) -> bool:
    t = text.lower().strip()
    if looks_like_compile(t):
        return False
    if re.search(r"\b(tbc|manual\s*review)\s+queue\b", t):
        return True
    if re.search(r"\b(show|list|open)\s+all\s+(tbc|manual\s*review)\b", t):
        return True
    if re.search(r"\b(open|go\s+to)\b.{0,40}\b(tbc|manual\s*review)\b", t):
        return True
    if re.search(r"\b(show|list|open)\b.{0,24}\b(tbc|manual\s*review)\b", t) and not re.search(
        r"\b(contested|weak|threshold|rules|zero|blocked|allow[\s-]?list|lost\s*margin|reason)\b",
        t,
    ):
        return True
    return False


def route_intent(text: str) -> str:
    if looks_like_compile(text):
        return "compile"
    if looks_like_clear_focus(text):
        return "clear"
    if looks_like_tbc_handoff(text):
        return "tbc"
    return "profile"


def looks_like_clear_focus(text: str) -> bool:
    t = text.lower().strip()
    if not t:
        return False
    if looks_like_compile(t) or looks_like_tbc_handoff(t):
        return False
    if re.match(r"^(clear|reset|remove)\b", t) and re.search(r"\b(focus|filter|filters)\b", t):
        return True
    if re.match(r"^clear\s*(it|this|all)?\s*$", t):
        return True
    if re.match(r"^show\s+all(\s+tickets)?\s*$", t):
        return True
    if re.match(r"^(remove|drop)\s+(the\s+)?(focus|filter)\b", t):
        return True
    if re.search(r"\b(clear|reset)\s+(the\s+)?(table\s+)?(focus|filter)\b", t):
        return True
    return False


def test_tbc_show_all_routes_to_tbc() -> None:
    assert route_intent("Show all tbc, and review them for categorization") == "tbc"


def test_clear_focus_routes() -> None:
    assert route_intent("clear focus") == "clear"
    assert route_intent("clear filter") == "clear"
    assert route_intent("show all") == "clear"
    assert route_intent("reset filter") == "clear"


def test_review_b2c_is_profile() -> None:
    assert route_intent("review B2C") == "profile"


def test_show_contested_is_profile_not_tbc() -> None:
    assert route_intent("show contested") == "profile"
    assert route_intent("show not contested") == "profile"


def test_map_phrase_is_compile() -> None:
    assert route_intent('Map "invoice delay" to Billing & Admin > Invoices and PO request') == "compile"


def test_vague_nl_goes_to_profile_not_compile() -> None:
    # Clarify is a *server* outcome after focus parse fails — never compile.
    assert route_intent("what should I do next?") == "profile"
    assert route_intent("gsdfsaf") == "profile"


def test_manual_review_phrase() -> None:
    assert route_intent("open manual review queue") == "tbc"
