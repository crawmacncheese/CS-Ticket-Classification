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


def test_ticket_preview_payload_includes_all_tbc_rows_beyond_slice() -> None:
    rows = []
    tbc_reasons = {}
    for i in range(300):
        rows.append(
            {
                "id": str(i),
                "subject": f"Ticket {i}",
                "description": "x",
                "tags": "[]",
                "Tier1_Segment": "B2C",
                "Tier2_Stream": "A",
                "Tier3_Cat": "B",
                "Tier4_Type": "TBC (Manual Review)" if i == 250 else "Other",
                "Granular_Tech_UI_Type": "N/A",
            }
        )
        if i == 250:
            tbc_reasons[str(i)] = "zero_candidate"

    html = ticket_preview_html(rows, tbc_reasons=tbc_reasons, limit=200)
    start = html.index('type="application/json" id="classify-ticket-preview-data">') + len(
        'type="application/json" id="classify-ticket-preview-data">'
    )
    end = html.index("</script>", start)
    payload = json.loads(html[start:end])
    assert len(payload["rows"]) == 200
    assert payload["tbc_total"] == 1
    assert [r["id"] for r in payload["tbc_rows"]] == ["250"]


def test_ticket_preview_payload_includes_all_category_rows_beyond_slice() -> None:
    rows = []
    target_tier4 = "Rate or Renewal Inquiry"
    for i in range(300):
        rows.append(
            {
                "id": str(i),
                "subject": f"Ticket {i}",
                "description": "x",
                "tags": "[]",
                "Tier1_Segment": "B2C",
                "Tier2_Stream": "A",
                "Tier3_Cat": "B",
                "Tier4_Type": target_tier4 if i == 250 else "Other",
                "Granular_Tech_UI_Type": "N/A",
            }
        )

    html = ticket_preview_html(rows, tbc_reasons={}, limit=200)
    start = html.index('type="application/json" id="classify-ticket-preview-data">') + len(
        'type="application/json" id="classify-ticket-preview-data">'
    )
    end = html.index("</script>", start)
    payload = json.loads(html[start:end])
    assert len(payload["rows"]) == 200
    category_rows = payload["category_rows"][target_tier4]
    assert len(category_rows) == 1
    assert category_rows[0]["id"] == "250"
