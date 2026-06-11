from __future__ import annotations

import ast
import json
from typing import Any


def parse_satisfaction_score(value: Any) -> str | None:
    """Return Zendesk satisfaction score (e.g. good, bad, offered) when present."""
    if value is None:
        return None
    if isinstance(value, dict):
        score = value.get("score")
        return str(score).strip().lower() if score is not None else None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.startswith("{"):
            parsed: Any
            try:
                parsed = ast.literal_eval(s)
            except (ValueError, SyntaxError):
                try:
                    parsed = json.loads(s)
                except json.JSONDecodeError:
                    return None
            if isinstance(parsed, dict):
                score = parsed.get("score")
                return str(score).strip().lower() if score is not None else None
    return None


def has_bad_satisfaction_rating(ticket: dict[str, Any]) -> bool:
    """True when the ticket has a Zendesk CSAT score of bad."""
    return parse_satisfaction_score(ticket.get("satisfaction_rating")) == "bad"
