from app.pipeline.steps import FEATURE_INVITE, with_invite
from app.services.tech_news import _ok


def test_every_sign_off_invites_viewers_to_get_featured_once():
    assert with_invite("That was Acme. For Cover Founder News, thank you for watching.") == (
        f"That was Acme. {FEATURE_INVITE} For Cover Founder News, thank you for watching."
    )
    assert with_invite("That was Acme.") == f"That was Acme. {FEATURE_INVITE}"
    assert with_invite("") == FEATURE_INVITE
    once = with_invite("That was Acme.")
    assert with_invite(once) == once


def test_ticker_headlines_skip_forum_posts_and_real_network_names():
    assert _ok("Chipmaker unveils a faster AI accelerator")
    assert not _ok("Show HN: my weekend project")
    assert not _ok("Short")
