"""Media packages (regional, organisation and campaign) that people can buy on the distribution page and in the app."""

import sqlalchemy as sa

from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "distribution_packages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="regional"),
        sa.Column("region", sa.String(30), nullable=False, server_default=""),
        sa.Column("campaign", sa.String(20), nullable=False, server_default=""),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("usd_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("standard_usd", sa.Numeric(12, 2), nullable=True),
        sa.Column("local_prices", sa.JSON, nullable=False),
        sa.Column("outlet_names", sa.JSON, nullable=False),
        sa.Column("outlet_ids", sa.JSON, nullable=False),
        sa.Column("includes", sa.JSON, nullable=False),
        sa.Column("ideal_for", sa.String(400), nullable=False, server_default=""),
        sa.Column("note", sa.String(600), nullable=False, server_default=""),
        sa.Column("slots_total", sa.Integer, nullable=True),
        sa.Column("slots_taken", sa.Integer, nullable=False, server_default="0"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("sort", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_distribution_packages_region", "distribution_packages", ["region"])
    from decimal import Decimal

    from app.models.base import new_id, utcnow
    from app.services.package_seed import PACKAGES

    now = utcnow()
    money = lambda v: Decimal(v) if v is not None else None  # noqa: E731
    op.bulk_insert(
        table,
        [
            {**p, "usd_price": money(p["usd_price"]), "standard_usd": money(p["standard_usd"]), "id": new_id(), "sort": i, "active": True, "created_at": now}
            for i, p in enumerate(PACKAGES)
        ],
    )


def downgrade():
    op.drop_index("ix_distribution_packages_region", table_name="distribution_packages")
    op.drop_table("distribution_packages")
