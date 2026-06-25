import json

from cs_tickets.portal_ticket_preview import _embed_json_for_script, ticket_preview_html


def test_embed_json_escapes_script_close_tag() -> None:
    blob = _embed_json_for_script({"description": "</script><script>alert(1)</script>"})
    assert "</script>" not in blob
    assert json.loads(blob)["description"] == "</script><script>alert(1)</script>"


def test_ticket_preview_html_survives_script_like_description() -> None:
    rows = [
        {
            "id": "99",
            "subject": "Test",
            "description": "</script><script>alert('xss')</script>",
            "tags": "[]",
            "Tier1_Segment": "B2C",
            "Tier2_Stream": "A",
            "Tier3_Cat": "B",
            "Tier4_Type": "TBC (Manual Review)",
            "Granular_Tech_UI_Type": "N/A",
        }
    ]
    html = ticket_preview_html(rows, tbc_reasons={"99": "zero_candidate"})
    assert "classify-ticket-preview-data" in html
    assert "</script><script>alert" not in html
    assert "<\\/script>" in html or "\\u003c/script" in html.lower() or "alert('xss')" in html
    start = html.index('id="classify-ticket-preview-data">') + len('id="classify-ticket-preview-data">')
    end = html.index("</script>", start)
    payload = json.loads(html[start:end])
    assert payload["rows"][0]["description"].startswith("</script>")
