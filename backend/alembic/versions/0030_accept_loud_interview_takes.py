"""Release usable recordings that were blocked solely for loud source audio."""

import sqlalchemy as sa

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    takes = sa.table(
        "takes",
        sa.column("status", sa.String),
        sa.column("flags", sa.JSON),
        sa.column("kind", sa.String),
        sa.column("processed_audio_key", sa.String),
        sa.column("processed_video_key", sa.String),
        sa.column("duration_s", sa.Numeric),
        sa.column("transcript", sa.Text),
    )
    # A single SQL update also protects against a concurrent owner-requested retake.
    # Other flags, missing media/transcripts and failed processing remain untouched.
    op.get_bind().execute(
        takes.update()
        .where(
            takes.c.status == "needs_retake",
            sa.cast(takes.c.flags, sa.String) == '["clipped_audio"]',
            takes.c.processed_audio_key.is_not(None),
            takes.c.processed_audio_key != "",
            takes.c.duration_s > 0,
            takes.c.transcript.is_not(None),
            sa.func.trim(takes.c.transcript) != "",
            sa.or_(
                takes.c.kind == "audio",
                sa.and_(
                    takes.c.kind == "video", takes.c.processed_video_key.is_not(None), takes.c.processed_video_key != ""
                ),
            ),
        )
        .values(status="ready")
    )


def downgrade():
    # Data-only correction: do not re-block recordings that may already be submitted or used in a video.
    pass
