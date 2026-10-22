"""Local development only: read the last email sent to an address (the sign-in code) from the in-memory mailbox."""

from fastapi import APIRouter, HTTPException

from app.integrations import registry
from app.integrations.email.mock import MockEmail

router = APIRouter(prefix="/v1/dev", tags=["dev"])


@router.get("/last-email")
async def last_email(to: str) -> dict:
    mail = registry.get_email()
    if not isinstance(mail, MockEmail):
        raise HTTPException(404)
    msgs = [m for m in mail.sent if m["to"].lower() == to.lower()]
    if not msgs:
        raise HTTPException(404, "No email yet")
    return msgs[-1]
