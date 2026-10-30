"""Apply the Nigerian outlet sheet final prices, including the margin exactly once."""

import copy
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

PRICES = {
    "23": "18.8",  # Tribune
    "24": "87.5",  # Sun
    "25": "60.0",  # New Telegraph
    "26": "18.8",  # Independent
    "27": "18.8",  # Vanguard
    "28": "27.0",  # ThisDay
    "29": "115.1",  # The Guardian
    "30": "128.8",  # Punch
    "31": "22.9",  # Daily Trust
    "32": "128.8",  # Daily Post
    "33": "101.3",  # Business Day
    "34": "18.8",  # P.M. News
    "35": "87.5",  # Premium Times
    "36": "73.8",  # The Nation
    "48": "87.5",  # Pilot Newspaper
    "49": "87.5",  # Leadership Newspaper
    "50": "115.1",  # AIT News
    "51": "115.1",  # TVC News
    "52": "137.1",  # The Daily Times
    "53": "651.6",  # Daily Nation
}
KEY = "distribution_fulfillment"
BACKUP = "distribution_credit_prices_0028"
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
        settings.insert().values(key=BACKUP, value={"previous": previous}, updated_by="migration:0028", updated_at=now)
    )
    db.execute(
        settings.update()
        .where(settings.c.key == KEY)
        .values(value=changed, updated_by="migration:0028", updated_at=now)
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
            .values(value=restored, updated_by="rollback:0028", updated_at=datetime.now(UTC))
        )
    db.execute(settings.delete().where(settings.c.key == BACKUP))
