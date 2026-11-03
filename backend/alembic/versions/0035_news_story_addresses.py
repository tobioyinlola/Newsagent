"""Published News Desk stories get a headline address (the-headline-words-<6 letters>), like every other story.

Their old address (cf-tech-<id>) keeps working: the site finds the story by the id inside it."""

import re
import unicodedata

import sqlalchemy as sa

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None

PLACEHOLDER = re.compile(r"^cf-tech-([0-9a-f]{32})$")


def _slug(headline: str, ident: str) -> str:
    plain = unicodedata.normalize("NFKD", headline).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    if len(words) > 70:
        words = words[:70].rsplit("-", 1)[0] or words[:70]
    return f"{words or 'story'}-{ident[:6]}"


def upgrade():
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, slug, published_data FROM news_desk_stories WHERE published_data IS NOT NULL")
    ).fetchall()
    for ident, slug, published in rows:
        if not PLACEHOLDER.fullmatch(slug or ""):
            continue
        data = published
        if isinstance(data, str):
            import json

            data = json.loads(data)
        headline = str((data or {}).get("headline") or "")
        if headline:
            bind.execute(
                sa.text("UPDATE news_desk_stories SET slug = :s WHERE id = :i"),
                {"s": _slug(headline, ident), "i": ident},
            )


def downgrade():
    pass  # addresses are not changed back; the old address still works either way
