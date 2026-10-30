"""Persisted delivery state makes confirmation emails retryable after a provider outage or process restart."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_maker
from app.models import DistributionRequest
from app.models.base import utcnow
from app.services.notifications import send_email


async def send_confirmation(db: AsyncSession, row: DistributionRequest) -> bool:
    if row.paid_at is None or row.email_sent_at is not None:
        return False
    sent = True
    for recipient in sorted({row.created_by, row.data["contact_email"]}):
        delivered = await send_email(
            recipient,
            "Your distribution request is confirmed",
            "Your distribution request has been submitted successfully. Someone from the Cover Founder team will reach out to you within the next 24 hours.",
        )
        sent = delivered and sent
    if sent:
        row.email_sent_at = utcnow()
        await db.commit()
    return sent


async def retry_confirmations() -> int:
    count = 0
    async with session_maker()() as db:
        rows = (
            (
                await db.execute(
                    select(DistributionRequest)
                    .where(
                        DistributionRequest.paid_at.is_not(None),
                        DistributionRequest.email_sent_at.is_(None),
                    )
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            count += int(await send_confirmation(db, row))
    return count
