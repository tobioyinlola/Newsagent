"""Only usable, processed takes blocked for loudness alone may be recovered."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa


def test_loud_take_recovery_preserves_other_flags_missing_media_and_manual_retakes():
    path = Path(__file__).parents[1] / "alembic/versions/0030_accept_loud_interview_takes.py"
    spec = importlib.util.spec_from_file_location("loud_take_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    takes = sa.Table(
        "takes",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("status", sa.String),
        sa.Column("flags", sa.JSON),
        sa.Column("kind", sa.String),
        sa.Column("processed_audio_key", sa.String),
        sa.Column("processed_video_key", sa.String),
        sa.Column("duration_s", sa.Numeric),
        sa.Column("transcript", sa.Text),
    )
    metadata.create_all(engine)
    base = {
        "status": "needs_retake",
        "flags": ["clipped_audio"],
        "kind": "video",
        "processed_audio_key": "audio.mp3",
        "processed_video_key": "video.mp4",
        "duration_s": 12,
        "transcript": "My business story",
    }
    rows = {
        "loud_video": {},
        "loud_audio": {"kind": "audio", "processed_video_key": None},
        "silent": {"flags": ["clipped_audio", "no_speech"]},
        "dark": {"flags": ["clipped_audio", "dark_video"]},
        "short": {"flags": ["clipped_audio", "too_short"]},
        "manual": {"flags": ["clipped_audio", "owner_requested"]},
        "unknown_flag": {"flags": ["clipped_audio", "unknown"]},
        "no_audio": {"processed_audio_key": None},
        "no_video": {"processed_video_key": ""},
        "no_duration": {"duration_s": None},
        "no_transcript": {"transcript": "  "},
        "failed": {"status": "failed"},
        "processing": {"status": "processing"},
        "ready": {"status": "ready"},
    }
    with engine.begin() as db, patch.object(migration.op, "get_bind", return_value=db):
        db.execute(takes.insert(), [{**base, **overrides, "id": id} for id, overrides in rows.items()])
        migration.upgrade()
        actual = {row.id: row.status for row in db.execute(sa.select(takes.c.id, takes.c.status))}
        for id, overrides in rows.items():
            expected = "ready" if id in {"loud_video", "loud_audio"} else overrides.get("status", "needs_retake")
            assert actual[id] == expected, id
        assert db.execute(sa.select(takes.c.flags).where(takes.c.id == "loud_video")).scalar_one() == ["clipped_audio"]
        migration.downgrade()
        assert db.execute(sa.select(takes.c.status).where(takes.c.id == "loud_video")).scalar_one() == "ready"
    engine.dispose()
