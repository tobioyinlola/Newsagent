"""The price rollout must preserve configured publisher policies and later admin edits."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa


def test_price_migration_updates_existing_overrides_and_rollback_preserves_later_edits():
    path = Path(__file__).parents[1] / "alembic/versions/0026_distribution_credit_prices.py"
    spec = importlib.util.spec_from_file_location("distribution_price_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    settings = sa.Table(
        "system_settings",
        metadata,
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", sa.JSON),
        sa.Column("updated_by", sa.String),
        sa.Column("updated_at", sa.DateTime),
    )
    metadata.create_all(engine)
    with engine.begin() as db, patch.object(migration.op, "get_bind", return_value=db):
        original = {
            "team_emails": ["sales@example.com"],
            "outlets": {
                "1": {"credits": "0", "accepts_logo": False, "contact_email": "editor@example.com"},
                "2": {"credits": "5", "email_body": "Publisher draft"},
                "18": {"credits": "123"},
            },
        }
        db.execute(settings.insert().values(key=migration.KEY, value=original, updated_at=datetime.now(UTC)))
        migration.upgrade()
        updated = db.execute(sa.select(settings.c.value).where(settings.c.key == migration.KEY)).scalar_one()
        assert updated["outlets"]["1"] == {**original["outlets"]["1"], "credits": "42"}
        assert updated["outlets"]["2"] == {**original["outlets"]["2"], "credits": "83"}
        assert updated["outlets"]["18"] == original["outlets"]["18"]
        assert updated["team_emails"] == original["team_emails"]
        assert "3" not in updated["outlets"]  # Do not silently confirm image policies for unconfigured outlets.
        updated["outlets"]["1"]["credits"] = "99"
        db.execute(settings.update().where(settings.c.key == migration.KEY).values(value=updated))
        migration.downgrade()
        restored = db.execute(sa.select(settings.c.value).where(settings.c.key == migration.KEY)).scalar_one()
        assert restored["outlets"]["1"]["credits"] == "99"
        assert restored["outlets"]["2"] == original["outlets"]["2"]
        assert restored["outlets"]["18"] == original["outlets"]["18"]
        assert (
            db.execute(sa.select(settings.c.key).where(settings.c.key == migration.BACKUP)).scalar_one_or_none() is None
        )
    engine.dispose()
