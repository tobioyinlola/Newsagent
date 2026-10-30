"""Operator-owned distribution configuration and authoritative, snapshot-friendly quotes."""

import hashlib
import json
from decimal import Decimal
from string import Formatter

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemSetting

KEY = "distribution_fulfillment"


class QuoteTooLarge(ValueError):
    pass


def version(items):
    values = [
        {
            k: o[k]
            for k in [
                "id",
                "credits",
                "accepts_logo",
                "accepts_images",
                "logo_credits",
                "picture_credits",
                "media_policy_configured",
            ]
        }
        for o in items
    ]
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


SUBJECT = "Publication enquiry: {headline}"
BODY = """Hello {contact_name},

I'm reaching out from Cover Founder with a sponsorship request for {outlet_name}. {payment_summary}

Headline: {headline}
Brief: {summary}

Press announcement:
{announcement}

Publication materials:
{assets}

Please confirm whether you can accept this placement, your publication timeline, the applicable sponsorship fee, and your bank/payment details so our team can arrange payment. Payment to your publication has not been confirmed by this email.

Please reply directly to this email; our team will coordinate the next steps with you.

Kind regards,
The Cover Founder team
Reference: {reference}"""
VARIABLES = {
    "contact_name",
    "outlet_name",
    "headline",
    "summary",
    "announcement",
    "assets",
    "reference",
    "payment_summary",
}


def check_template(value: str) -> str:
    try:
        for _, name, spec, conversion in Formatter().parse(value):
            if name is not None and (name not in VARIABLES or spec or conversion):
                raise ValueError(
                    "Use only the supported template placeholders, without formatting or attribute access."
                )
    except ValueError as e:
        raise ValueError(
            "Invalid email template. Use supported placeholders such as {headline} and {outlet_name}."
        ) from e
    return value


class OutletConfig(BaseModel):
    credits: Decimal = Field(default=Decimal("0"), ge=0, le=1000000, decimal_places=4)
    accepts_logo: bool = True
    accepts_images: bool = True
    logo_credits: Decimal = Field(default=Decimal("0"), ge=0, le=1000000, decimal_places=4)
    picture_credits: Decimal = Field(default=Decimal("0"), ge=0, le=1000000, decimal_places=4)
    direct_access: bool = False
    contact_name: str = Field(default="", max_length=200)
    contact_email: EmailStr | None = None
    email_subject: str = Field(default=SUBJECT, min_length=1, max_length=250)
    email_body: str = Field(default=BODY, min_length=1, max_length=12000)

    @field_validator("email_subject", "email_body")
    @classmethod
    def template(cls, value):
        if not value.strip():
            raise ValueError("Email subject and body cannot be blank.")
        return check_template(value)

    @field_validator("email_subject")
    @classmethod
    def subject_line(cls, value):
        if "\n" in value or "\r" in value:
            raise ValueError("Subject must be a single line.")
        return value

    @model_validator(mode="after")
    def recipient(self):
        if self.direct_access and not self.contact_email:
            raise ValueError("Add a contact email before enabling automatic outreach.")
        return self


class TeamConfig(BaseModel):
    team_emails: list[EmailStr] = Field(default_factory=list, max_length=20)


async def settings(db: AsyncSession, *, lock=False) -> SystemSetting | None:
    query = select(SystemSetting).where(SystemSetting.key == KEY)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(query)).scalar_one_or_none()


async def catalog(db: AsyncSession, *, admin=False) -> list[dict]:
    from app.routes.distribution import OUTLETS

    row = await settings(db)
    overrides = (row.value if row else {}).get("outlets", {})
    result = []
    for id, base in OUTLETS.items():
        config = OutletConfig.model_validate({"credits": base["credits"], **overrides.get(id, {})})
        value = config.model_dump(mode="json")
        if not admin:
            value = {
                k: value[k] for k in ["credits", "accepts_logo", "accepts_images", "logo_credits", "picture_credits"]
            }
        result.append({**base, **value, "media_policy_configured": id in overrides})
    return result


def quote(data: dict, outlets: list[dict]) -> list[dict]:
    lines = []
    choices = data.get("media_options", {})
    for outlet in outlets:
        if outlet["id"] not in data["outlet_ids"]:
            continue
        choice = choices.get(outlet["id"], {})
        confirmed = outlet.get("media_policy_configured", True)
        logo = bool(confirmed and data.get("logo_key") and outlet["accepts_logo"] and choice.get("include_logo", True))
        pictures = (
            data.get("picture_keys", [])
            if confirmed and outlet["accepts_images"] and choice.get("include_pictures", True)
            else []
        )
        base = Decimal(outlet["credits"])
        logo_fee = Decimal(outlet["logo_credits"]) if logo else Decimal(0)
        picture_fee = Decimal(outlet["picture_credits"]) * len(pictures)
        lines.append(
            {
                **{
                    k: outlet[k]
                    for k in [
                        "id",
                        "name",
                        "region",
                        "accepts_logo",
                        "accepts_images",
                        "logo_credits",
                        "picture_credits",
                        "media_policy_configured",
                    ]
                },
                "base_credits": str(base),
                "logo_fee": str(logo_fee),
                "picture_fee": str(picture_fee),
                "include_logo": logo,
                "picture_count": len(pictures),
                "picture_keys": list(pictures),
                "logo_key": data.get("logo_key") if logo else None,
                "credits": str(base + logo_fee + picture_fee),
            }
        )
    if sum((Decimal(line["credits"]) for line in lines), Decimal(0)) > Decimal("99999999.9999"):
        raise QuoteTooLarge(
            "The selected outlets exceed the checkout credit limit. Reduce the selection or contact support."
        )
    return lines
