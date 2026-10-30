"""Apply the owner's Credit on CF prices without changing publisher settings or paid orders."""

import copy
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None

PRICES = dict(
    zip(
        map(str, range(1, 18)),
        map(str, [42, 83, 124, 69, 97, 61, 138, 28, 42, 42, 28, 28, 42, 42, 42, 42, 42]),
        strict=True,
    )
)
KEY = "distribution_fulfillment"
BACKUP = "distribution_credit_prices_0026"
settings = sa.table(
    "system_settings",
    sa.column("key", sa.String),
    sa.column("value", sa.JSON),
    sa.column("updated_by", sa.String),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def upgrade():
    db = op.get_bind()
    current = db.execute(sa.select(settings.c.value).where(settings.c.key == KEY)).scalar_one_or_none()
    if current is None:
        return  # Outlets without explicit overrides inherit the new application defaults.
    changed = copy.deepcopy(current)
    previous = {}
    for id, price in PRICES.items():
        outlet = changed.get("outlets", {}).get(id)
        if outlet is not None:
            previous[id] = {"had_credits": "credits" in outlet, "credits": outlet.get("credits")}
            outlet["credits"] = price
    if not previous:
        return
    now = datetime.now(UTC)
    db.execute(
        settings.insert().values(key=BACKUP, value={"previous": previous}, updated_by="migration:0026", updated_at=now)
    )
    db.execute(
        settings.update()
        .where(settings.c.key == KEY)
        .values(value=changed, updated_by="migration:0026", updated_at=now)
    )


def downgrade():
    db = op.get_bind()
    backup = db.execute(sa.select(settings.c.value).where(settings.c.key == BACKUP)).scalar_one_or_none()
    if backup is None:
        return
    current = db.execute(sa.select(settings.c.value).where(settings.c.key == KEY)).scalar_one_or_none()
    if current is not None:
        restored = copy.deepcopy(current)
        for id, old in backup["previous"].items():
            outlet = restored.get("outlets", {}).get(id)
            # Preserve any subsequent admin pricing changes, as well as every non-price field.
            if outlet is not None and outlet.get("credits") == PRICES[id]:
                if old["had_credits"]:
                    outlet["credits"] = old["credits"]
                else:
                    outlet.pop("credits", None)
        db.execute(
            settings.update()
            .where(settings.c.key == KEY)
            .values(value=restored, updated_by="rollback:0026", updated_at=datetime.now(UTC))
        )
    db.execute(settings.delete().where(settings.c.key == BACKUP))
