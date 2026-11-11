"""Marketing copy: subject, preview line, body and button, with merge tags like {{first_name|there}}.

Tags are checked when the copy is saved, never at send time: an unknown tag is refused, and a tag that can come out empty
(someone's first name) must carry a fallback after a bar, so nobody gets "Hi ,"."""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Project, User, Workspace
from app.services import email_templates as templates

CATEGORIES = {
    "onboarding": "Onboarding",
    "activation": "Getting started",
    "billing": "Credits and billing",
    "win_back": "Win-back",
    "product": "Product news",
}
TAG = re.compile(r"\{\{\s*([A-Za-z_]+)\s*(?:\|([^{}]*))?\}\}")


class Invalid(ValueError):
    """The copy can't be saved; the message is shown to the operator."""


@dataclass(frozen=True)
class Tag:
    key: str
    label: str
    can_be_empty: bool  # such a tag must be written with a fallback: {{first_name|there}}
    sample: str


TAGS: tuple[Tag, ...] = (
    Tag("first_name", "First name", True, "Ada"),
    Tag("company", "Company name", False, "Acme Foods"),
    Tag("credits_left", "Credits left", False, "4"),
    Tag("videos_started", "Videos started", False, "2"),
)
BY_KEY = {t.key: t for t in TAGS}


class Wording(Protocol):
    """What an email is made from: a CopyIn being edited, or a saved version."""

    subject: str
    preheader: str
    body: str
    button_label: str
    button_url: str


class CopyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = "product"
    subject: str = Field(min_length=1, max_length=200)
    preheader: str = Field("", max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    button_label: str = Field("", max_length=60)
    button_url: str = Field("", max_length=500)


def check_tags(text: str, what: str) -> None:
    for m in TAG.finditer(text):
        t = BY_KEY.get(m.group(1))
        if t is None:
            raise Invalid(f"{what}: {{{{{m.group(1)}}}}} isn't a tag we know. Use the buttons to add one.")
        if t.can_be_empty and not (m.group(2) or "").strip():
            raise Invalid(
                f"{what}: write a fallback for {{{{{t.key}}}}}, like {{{{{t.key}|there}}}}, for people we don't have it for."
            )
    leftover = TAG.sub("", text)
    if "{{" in leftover or "}}" in leftover:
        raise Invalid(f"{what}: there's a stray {{{{ or }}}}. A tag looks like {{{{first_name|there}}}}.")


def validate(c: CopyIn) -> CopyIn:
    if c.category not in CATEGORIES:
        raise Invalid("Choose a category from the list.")
    c.name, c.subject, c.preheader = c.name.strip(), c.subject.strip(), c.preheader.strip()
    c.body, c.button_label, c.button_url = c.body.strip(), c.button_label.strip(), c.button_url.strip()
    if not c.name or not c.subject or not c.body:
        raise Invalid("A name, a subject and a message are needed.")
    if "\n" in c.subject or "\r" in c.subject or "\n" in c.preheader:
        raise Invalid("The subject and the preview line must be one line.")
    for what, text in (
        ("Subject", c.subject),
        ("Preview line", c.preheader),
        ("Message", c.body),
        ("Button text", c.button_label),
    ):
        check_tags(text, what)
    if bool(c.button_label) != bool(c.button_url):
        raise Invalid("A button needs both its text and its link, or neither.")
    if c.button_url:
        if "{{" in c.button_url:
            raise Invalid("The button link can't contain tags.")
        if not (c.button_url.startswith("/") and not c.button_url.startswith("//")) and not c.button_url.startswith(
            "https://"
        ):
            raise Invalid("The button link must start with https:// or with / for a page on our site.")
    return c


def fill(text: str, values: dict[str, str]) -> str:
    """Put each tag's value in; a missing or empty value uses the fallback written after the bar."""

    def one(m: re.Match) -> str:
        return (values.get(m.group(1)) or "").strip() or (m.group(2) or "").strip()

    return TAG.sub(one, text)


def sample_values() -> dict[str, str]:
    return {t.key: t.sample for t in TAGS}


async def values_for(db: AsyncSession, user: User) -> dict[str, str]:
    """The real values for one person. Their first name is the first word of the founder name on their latest video, if any."""
    ws = await db.get(Workspace, user.workspace_id)
    founder = (
        await db.execute(
            select(Project.founder_name)
            .where(Project.workspace_id == user.workspace_id, Project.founder_name != "")
            .order_by(Project.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    started = (await db.execute(select(Project.id).where(Project.workspace_id == user.workspace_id))).all()
    first = (founder or "").split()[0] if founder and founder.split() else ""
    left = ws.credit_balance if ws else Decimal(0)
    return {
        "first_name": first,
        "company": ws.name if ws else "",
        "credits_left": f"{left.normalize():f}" if left else "0",
        "videos_started": str(len(started)),
    }


def fields_for(c: Wording, values: dict[str, str]) -> dict:
    """The copy with one person's details filled in, as the parts an email is made from."""
    url = c.button_url
    if url.startswith("/"):
        url = get_settings().app_base_url.rstrip("/") + url
    return {
        "subject": fill(c.subject, values),
        "preheader": fill(c.preheader, values),
        "body": fill(c.body, values),
        "button": (fill(c.button_label, values), url) if c.button_label else None,
    }


def rendered(c: Wording, values: dict[str, str]) -> dict[str, str]:
    """The finished email for one set of values: {subject, preheader, text, html}. Works on a CopyIn or a stored version."""
    f = fields_for(c, values)
    html, text = templates.render(
        f["subject"],
        f["body"],
        button=f["button"],
        preheader=f["preheader"],
        footer="You are receiving this because you have a Cover Founder account. You can stop these emails at any time.",
        footer_link=("Unsubscribe", get_settings().app_base_url.rstrip("/") + "/v1/unsubscribe/preview"),
    )
    return {"subject": f["subject"], "preheader": f["preheader"], "text": text, "html": html}
