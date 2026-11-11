"""Cookie-free website visitor counts: daily visitor markers (short-lived), and daily totals by page and by source."""

import sqlalchemy as sa

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "site_visit_marks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("visitor_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("day", "visitor_hash"),
    )
    op.create_index("ix_site_visit_marks_day", "site_visit_marks", ["day"])
    op.create_table(
        "site_daily",
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("visitors", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("pageviews", sa.BigInteger, nullable=False, server_default="0"),
    )
    op.create_table(
        "site_page_daily",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("path", sa.String(120), nullable=False),
        sa.Column("views", sa.BigInteger, nullable=False, server_default="0"),
        sa.UniqueConstraint("day", "path"),
    )
    op.create_index("ix_site_page_daily_day", "site_page_daily", ["day"])
    op.create_table(
        "site_source_daily",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("detail", sa.String(100), nullable=False, server_default=""),
        sa.Column("visitors", sa.BigInteger, nullable=False, server_default="0"),
        sa.UniqueConstraint("day", "source", "detail"),
    )
    op.create_index("ix_site_source_daily_day", "site_source_daily", ["day"])


def downgrade():
    op.drop_table("site_source_daily")
    op.drop_table("site_page_daily")
    op.drop_table("site_daily")
    op.drop_table("site_visit_marks")
