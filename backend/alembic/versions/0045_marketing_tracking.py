"""Marketing open and click tracking: a token per email and what came back."""

import sqlalchemy as sa

from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("marketing_sends") as b:
        b.add_column(sa.Column("track_token", sa.String(40), nullable=True))
        b.add_column(sa.Column("click_url", sa.Text, nullable=True))
        b.add_column(sa.Column("open_count", sa.Integer, nullable=False, server_default="0"))
        b.add_column(sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("click_count", sa.Integer, nullable=False, server_default="0"))
        b.add_column(sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True))
        b.create_unique_constraint("uq_marketing_sends_track_token", ["track_token"])


def downgrade():
    with op.batch_alter_table("marketing_sends") as b:
        b.drop_constraint("uq_marketing_sends_track_token", type_="unique")
        for c in ("clicked_at", "click_count", "opened_at", "open_count", "click_url", "track_token"):
            b.drop_column(c)
