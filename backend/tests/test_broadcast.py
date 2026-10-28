from app.pipeline.steps import FEATURE_INVITE, presenter_identity, with_invite
from app.services.cf_news import _ok


def test_every_sign_off_invites_viewers_to_get_featured_once():
    assert with_invite("That was Acme. For Cover Founder News, thank you for watching.") == (
        f"That was Acme. {FEATURE_INVITE} For Cover Founder News, thank you for watching."
    )
    assert with_invite("That was Acme.") == f"That was Acme. {FEATURE_INVITE}"
    assert with_invite("") == FEATURE_INVITE
    once = with_invite("That was Acme.")
    assert with_invite(once) == once


def test_ticker_headlines_skip_empty_and_banned_lines():
    assert _ok("Acme Farms raises $5M to bring farmers online")
    assert not _ok("Short")


def test_the_house_presenter_is_marcus_richard_lead_btn_director(monkeypatch):
    from app.config import get_settings
    from app.models import Project

    monkeypatch.setattr(
        get_settings(), "heygen_featured_presenters", "look1|Marcus, news desk|male;look2|Elena, news desk|female"
    )
    p = Project(anchor_id="look1")
    assert presenter_identity(p) == {"name": "Marcus Richard", "title": "Lead BTN Director, CF"}
    assert presenter_identity(Project(anchor_id="look2")) == {"name": "Elena", "title": "Presenter, CF"}


def test_closing_params_are_read_from_the_environment_setting(monkeypatch):
    from app.config import get_settings
    from app.pipeline.steps import closing_params

    monkeypatch.setattr(get_settings(), "heygen_closing_params", '{"expression": "smile"}')
    assert closing_params() == {"expression": "smile"}
    monkeypatch.setattr(get_settings(), "heygen_closing_params", "not json")
    assert closing_params() is None
    monkeypatch.setattr(get_settings(), "heygen_closing_params", "")
    assert closing_params() is None
