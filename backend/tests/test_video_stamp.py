"""The date and time stamp and the LIVE badge that every video carries."""

from datetime import UTC, datetime

from app.pipeline.steps import published_label


def test_the_stamp_reads_like_a_news_channel_in_the_channels_time_zone():
    assert published_label(datetime(2026, 10, 29, 14, 42, tzinfo=UTC)) == "OCT 29, 2026 · 10:42 AM EDT"
    assert published_label(datetime(2026, 12, 1, 3, 5, tzinfo=UTC)) == "NOV 30, 2026 · 10:05 PM EST"
    assert published_label(datetime(2026, 10, 29, 16, 0, tzinfo=UTC)).startswith("OCT 29, 2026 · 12:00 PM")
