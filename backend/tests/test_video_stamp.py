"""The date and time stamp and the LIVE badge that every video carries."""

from datetime import UTC, datetime

from app.pipeline.steps import published_label


def test_the_stamp_reads_like_a_news_channel_in_the_channels_time_zone():
    assert published_label(datetime(2026, 10, 29, 14, 42, tzinfo=UTC)) == "OCT 29, 2026 · 10:42 AM EDT"
    assert published_label(datetime(2026, 12, 1, 3, 5, tzinfo=UTC)) == "NOV 30, 2026 · 10:05 PM EST"
    assert published_label(datetime(2026, 10, 29, 16, 0, tzinfo=UTC)).startswith("OCT 29, 2026 · 12:00 PM")


def test_sign_in_code_emails_are_plain_notes_not_designed_mail():
    from app.services.email_templates import sign_in_code

    subject, html, text = sign_in_code("signup", "123456", 10)
    assert "123456" in subject and "123456" in html and "123456" in text
    assert "<img" not in html and "<table" not in html and "<a " not in html  # no logo picture, layout or links
