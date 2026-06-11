from cs_tickets.satisfaction import has_bad_satisfaction_rating, parse_satisfaction_score


def test_parse_satisfaction_score_from_dict() -> None:
    assert parse_satisfaction_score({"score": "bad", "id": 1}) == "bad"
    assert parse_satisfaction_score({"score": "good"}) == "good"
    assert parse_satisfaction_score({"score": "offered"}) == "offered"


def test_parse_satisfaction_score_from_string() -> None:
    s = "{'score': 'bad', 'id': 57709674553241, 'comment': None, 'reason': 'No reason provided'}"
    assert parse_satisfaction_score(s) == "bad"


def test_parse_satisfaction_score_missing() -> None:
    assert parse_satisfaction_score(None) is None
    assert parse_satisfaction_score("") is None
    assert parse_satisfaction_score({}) is None


def test_has_bad_satisfaction_rating() -> None:
    assert has_bad_satisfaction_rating({"satisfaction_rating": {"score": "bad"}}) is True
    assert has_bad_satisfaction_rating({"satisfaction_rating": {"score": "good"}}) is False
    assert has_bad_satisfaction_rating({}) is False
