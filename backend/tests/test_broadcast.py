from app.pipeline.steps import presenter_identity
from app.services.cf_news import _ok


def test_no_sign_off_invites_viewers_to_get_featured_any_more():
    from types import SimpleNamespace

    from app.pipeline import steps
    from app.services import script_polish as polish

    segs = [{"kind": "outro", "text": "That was Acme. For Cover Founder News, thank you for watching."}]
    assert steps.segment_texts(SimpleNamespace(segments=segs))["outro"] == segs[0]["text"]  # spoken as written
    asked = [
        {"kind": "outro", "text": "Thanks, Ada. If you want to get featured on Cover Founder, get in touch. Goodnight."}
    ]
    out = steps.segment_texts(SimpleNamespace(segments=asked))["outro"]
    assert out == "Thanks, Ada. Goodnight." and not polish.has_invite(out)  # an invitation the writer added is dropped


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
    assert presenter_identity(p) == {"name": "Marcus Richard", "title": "Business Reporter, CF News"}
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
