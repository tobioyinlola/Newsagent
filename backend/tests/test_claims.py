from app.services.claims import detect_claims


def test_flags_numbers_and_superlatives():
    cats = {
        c.category
        for c in detect_claims(
            "We raised $2M in seed funding. We serve 10,000 customers. We are the first and the fastest."
        )
    }
    assert {"revenue", "funding", "users", "superlative"} <= cats


def test_plain_text_has_no_flags():
    assert detect_claims("Tonight we meet a team building tools for farmers.") == []
