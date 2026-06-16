"""Shared HTML shell and top navigation for the CS Tickets portal."""

from __future__ import annotations

from typing import Literal

from cs_tickets.drive_upload import drive_runs_folder_url
from cs_tickets.portal_copy import (
    NAV_CATEGORIZE,
    NAV_REFERENCE_CATEGORIES,
    NAV_RUN_HISTORY,
    NAV_TBC_TRENDS,
)

NavActive = Literal["categorize", "learn", "dashboard"]


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def portal_head(*, title: str, extra_scripts: list[str] | None = None) -> str:
    scripts = ""
    if extra_scripts:
        scripts = "\n".join(f'<script src="{_esc(s)}" defer></script>' for s in extra_scripts)
    return f"""<meta charset="utf-8">
    <title>{_esc(title)}</title>
    <link rel="stylesheet" href="/static/agent_theme_1.css">
    <link rel="stylesheet" href="/static/cs_tickets_theme.css?v=2">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&amp;family=JetBrains+Mono:wght@400&amp;family=Playfair+Display:wght@700&amp;display=swap" rel="stylesheet">
    {scripts}"""


def portal_nav(*, active: NavActive | None = None) -> str:
    def item(href: str, label: str, key: NavActive) -> str:
        if active == key:
            cls = "btn btn-primary portal-topnav-link nav-active"
        else:
            cls = "btn btn-secondary portal-topnav-link"
        return f'<a href="{href}" class="{cls}">{_esc(label)}</a>'

    drive_url = _esc(drive_runs_folder_url())
    return f"""<header class="portal-header">
    <p class="portal-brand">CS Tickets</p>
    <nav class="portal-topnav" aria-label="Portal sections">
        {item("/", NAV_CATEGORIZE, "categorize")}
        {item("/learn", NAV_REFERENCE_CATEGORIES, "learn")}
        {item("/dashboard", NAV_TBC_TRENDS, "dashboard")}
        <span class="portal-topnav-spacer" aria-hidden="true"></span>
        <a href="{drive_url}" class="btn btn-secondary portal-topnav-link portal-topnav-external" target="_blank" rel="noopener noreferrer">{_esc(NAV_RUN_HISTORY)}</a>
    </nav>
</header>"""


def portal_page_html(
    *,
    title: str,
    body: str,
    active: NavActive | None = None,
    body_class: str = "",
    main_class: str = "",
    extra_scripts: list[str] | None = None,
    include_nav: bool = True,
) -> str:
    head = portal_head(title=title, extra_scripts=extra_scripts)
    body_cls = f' class="{body_class}"' if body_class else ""
    main_parts = ["container", "portal-main"]
    if main_class:
        main_parts.append(main_class)
    main_cls = " ".join(main_parts)
    nav = portal_nav(active=active) if include_nav else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>{head}</head>
<body{body_cls}>
<div class="portal-shell">
    {nav}
    <div class="{main_cls}">
        {body}
    </div>
</div>
</body></html>"""
