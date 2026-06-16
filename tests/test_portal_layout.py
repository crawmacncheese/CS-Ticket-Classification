"""Tests for shared portal layout and top navigation."""

from fastapi.testclient import TestClient

from cs_tickets.portal_app import app
from cs_tickets.portal_copy import NAV_CATEGORIZE, NAV_REFERENCE_CATEGORIES, NAV_TBC_TRENDS
from cs_tickets.portal_layout import portal_nav, portal_page_html

client = TestClient(app)


def test_portal_nav_renders_three_sections() -> None:
    html = portal_nav(active="learn")
    assert NAV_CATEGORIZE in html
    assert NAV_REFERENCE_CATEGORIES in html
    assert NAV_TBC_TRENDS in html
    assert 'href="/"' in html
    assert 'href="/learn"' in html
    assert 'href="/dashboard"' in html
    assert "nav-active" in html
    assert html.count("nav-active") == 1


def test_portal_page_html_includes_shell() -> None:
    html = portal_page_html(title="Test", body="<p>body</p>", active="categorize")
    assert "portal-shell" in html
    assert "portal-header" in html
    assert "portal-topnav" in html
    assert "portal-main" in html
    assert "<p>body</p>" in html


def test_all_main_routes_share_top_nav() -> None:
    for path in ("/", "/learn", "/dashboard"):
        r = client.get(path)
        assert r.status_code == 200
        assert "portal-topnav" in r.text
        assert "portal-header" in r.text
        assert NAV_CATEGORIZE in r.text
        assert NAV_REFERENCE_CATEGORIES in r.text
        assert NAV_TBC_TRENDS in r.text
