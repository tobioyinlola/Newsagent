"""Record which Terms of Use and Privacy Policy version a person agreed to at sign-up, and when."""

import sqlalchemy as sa

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("auth_codes", sa.Column("terms_version", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("terms_version", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "terms_version")
    op.drop_column("auth_codes", "terms_version")
