"""Portal role affordances until ingress SSO exists."""

from __future__ import annotations

import os


def portal_allow_confirm() -> bool:
    """When false, analysts may compile/preview rules but cannot Confirm or disable live rules."""
    value = os.environ.get("PORTAL_ALLOW_CONFIRM", "").strip().lower()
    return value in ("1", "true", "yes", "lead")


def tbc_auto_suggest_enabled() -> bool:
    """Auto-run AI category suggestions on the TBC queue when compile LLM is configured."""
    from cs_tickets.rule_compile import compile_llm_configured

    if os.environ.get("TBC_AUTO_SUGGEST", "1").strip().lower() in ("0", "false", "no"):
        return False
    return compile_llm_configured()
