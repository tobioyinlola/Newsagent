"""Where outlets' replies arrive: a webhook that any inbound-mail provider (or a small forwarder) can post to."""

import base64
import hashlib
import hmac
import json
import logging
import time

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.services import outreach, outreach_inbound
from app.services.notifications import notify_operators
from app.services.ratelimit import limit

log = logging.getLogger("outreach")
router = APIRouter(tags=["outreach"])
TOLERANCE_S = 300


class InboundIn(BaseModel):
    to: list[str] | str
    sender: str = Field(alias="from", max_length=500)
    subject: str = Field(default="", max_length=1000)
    text: str = Field(default="", max_length=400000)
    message_id: str | None = Field(default=None, max_length=300)
    in_reply_to: str | None = Field(default=None, max_length=300)
    references: str = Field(default="", max_length=4000)
    headers: dict[str, str] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    def mail(self) -> outreach_inbound.InboundMail:
        return outreach_inbound.InboundMail(
            to=[self.to] if isinstance(self.to, str) else list(self.to),
            sender=self.sender,
            subject=self.subject,
            text=self.text,
            message_id=self.message_id,
            in_reply_to=self.in_reply_to,
            references=self.references,
            headers=self.headers,
        )


def verify_svix(secret: str, headers: dict[str, str], body: bytes, now: float | None = None) -> bool:
    """The signature scheme Resend (via Svix) uses for webhooks: HMAC-SHA256 over `id.timestamp.body`, base64, `v1,<sig>`."""
    mid, ts, sigs = headers.get("svix-id", ""), headers.get("svix-timestamp", ""), headers.get("svix-signature", "")
    if not (mid and ts and sigs and secret.startswith("whsec_")):
        return False
    try:
        if abs((now or time.time()) - int(ts)) > TOLERANCE_S:
            return False
        key = base64.b64decode(secret[len("whsec_") :])
    except (ValueError, TypeError):
        return False
    expected = base64.b64encode(hmac.new(key, f"{mid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return any(hmac.compare_digest(expected, part.split(",", 1)[-1]) for part in sigs.split())


async def _resend_mail(event: dict) -> outreach_inbound.InboundMail:
    """A Resend `email.received` event. If the event carries no body, the message is fetched with the API key."""
    data = event.get("data") or {}
    text = data.get("text") or ""
    headers = (
        {str(k): str(v) for k, v in (data.get("headers") or {}).items()}
        if isinstance(data.get("headers"), dict)
        else {}
    )
    if not text and data.get("email_id"):
        async with httpx.AsyncClient(
            base_url="https://api.resend.com",
            headers={"Authorization": f"Bearer {get_settings().email_api_key}"},
            timeout=15,
        ) as c:
            r = await c.get(f"/emails/receiving/{data['email_id']}")
            r.raise_for_status()
            full = r.json()
        text = full.get("text") or full.get("html") or ""
        data = {**data, **{k: v for k, v in full.items() if v}}
        if isinstance(full.get("headers"), dict):
            headers = {str(k): str(v) for k, v in full["headers"].items()}
    to = data.get("to") or []
    return outreach_inbound.InboundMail(
        to=[to] if isinstance(to, str) else [str(x) for x in to],
        sender=str(data.get("from") or ""),
        subject=str(data.get("subject") or ""),
        text=str(text),
        message_id=data.get("message_id") or headers.get("Message-ID") or headers.get("message-id"),
        in_reply_to=headers.get("In-Reply-To") or headers.get("in-reply-to"),
        references=headers.get("References") or headers.get("references") or "",
        headers=headers,
    )


@router.post("/v1/webhooks/inbound-email", dependencies=[Depends(limit("inbound-email", 600, 60))])
async def inbound_email(request: Request, tasks: BackgroundTasks, db: AsyncSession = Depends(get_session)) -> dict:
    secret = get_settings().outreach_inbound_secret
    if not outreach.enabled() or not secret:
        raise HTTPException(404)
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        if "svix-signature" in headers:
            if not verify_svix(secret, headers, body):
                raise HTTPException(401, "Invalid signature")
            event = json.loads(body)
            if event.get("type") != "email.received":
                return {"result": "ignored"}
            mail = await _resend_mail(event)
        else:
            if not hmac.compare_digest(headers.get("x-inbound-secret", ""), secret):
                raise HTTPException(401, "Invalid secret")
            mail = InboundIn.model_validate(json.loads(body)).mail()
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(400, "Malformed message") from e
    except httpx.HTTPError as e:
        raise HTTPException(503, "Could not fetch the message; try again") from e  # the provider retries
    result = await outreach_inbound.receive(db, mail)
    await db.commit()
    if result["result"] in {"stored", "opt_out"}:
        tasks.add_task(_announce, result)
    return {"result": result["result"]}


async def _announce(result: dict) -> None:
    """Tell the team a reply arrived (the agent, when it is on, reads it too)."""
    try:
        subject = "An outlet asked us to stop" if result["result"] == "opt_out" else "An outlet replied"
        await notify_operators(
            subject, f"Open the Outreach inbox in the back office to read it: {get_settings().admin_base_url}/outreach"
        )
    except Exception:  # noqa: BLE001
        log.exception("could not announce a reply")
