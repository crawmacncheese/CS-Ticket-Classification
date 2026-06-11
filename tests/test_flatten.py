from cs_tickets.flatten import flatten_ticket


def test_flatten_tags_json_string():
    ticket = {
        "url": "https://example.com/1.json",
        "id": 1,
        "tags": ["a", "b"],
        "follower_ids": [10, 20],
        "has_incidents": False,
        "is_public": True,
    }
    row = flatten_ticket(ticket)
    assert row["tags"] == '["a","b"]'
    assert row["follower_ids"] == "[10,20]"
    assert row["has_incidents"] is False
    assert row["is_public"] is True


def test_flatten_empty_tags():
    row = flatten_ticket({"id": 2, "tags": None})
    assert row["tags"] is None
