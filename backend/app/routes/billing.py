"""Credits: what can be bought, checkout, payment webhook, ledger and usage statements."""

import csv
import io
import json
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.config import get_settings
from app.db import get_session
from app.integrations import registry
from app.integrations.billing.base import InvalidSignature
from app.integrations.billing.mock import SIGNATURE_HEADER, sign
from app.models import Checkout, CreditTransaction, User, Workspace
from app.schemas.api import (
    BillingSummary,
    CheckoutIn,
    CheckoutOut,
    CreditOptionOut,
    LedgerEntry,
    UsageLine,
    UsageStatement,
)
from app.services import credits, ledger
from app.services.audit import audit
from app.services.notifications import send_email
from app.services.ratelimit import limit

router = APIRouter(tags=["billing"])


def _options() -> list[CreditOptionOut]:
    return [
        CreditOptionOut(amount_usd=o.amount_usd, credits=o.credits, videos=o.videos) for o in credits.purchase_options()
    ]


@router.get("/v1/billing/options", response_model=list[CreditOptionOut])
async def options(_: Principal = Depends(current_principal)) -> list[CreditOptionOut]:
    """What can be bought: fixed amounts, each with the credits it gives."""
    return _options()


@router.get(
    "/v1/public/credit-options",
    response_model=list[CreditOptionOut],
    dependencies=[Depends(limit("public-packs", 120, 600))],
)
async def public_options() -> list[CreditOptionOut]:
    """The same, for the public pricing section of the landing page (no sign-in needed)."""
    return _options()


@router.get("/v1/public/stats", dependencies=[Depends(limit("public-packs", 120, 600))])
async def public_stats(session: AsyncSession = Depends(get_session)) -> dict:
    """Live numbers for the public site: videos finished, and how often shared videos have been opened."""
    from app.models import Project, ShareLink

    videos = (await session.execute(select(func.count()).where(Project.state == "final_ready"))).scalar_one()
    views = (await session.execute(select(func.coalesce(func.sum(ShareLink.views), 0)))).scalar_one()
    return {"videos": int(videos), "impressions": int(views)}


@router.get("/v1/billing/summary", response_model=BillingSummary)
async def summary(p: Principal = Depends(current_principal)) -> BillingSummary:
    w = p.workspace
    return BillingSummary(
        credit_balance=w.credit_balance,
        spend_cap=w.spend_cap,
        spent_total=w.spent_total,
        low_balance_threshold=Decimal(get_settings().low_balance_threshold),
        credits_per_video=credits.credits_per_video(),
        usd_per_credit=credits.usd_per_credit(),
        videos_left=credits.videos_for(w.credit_balance),
    )


@router.post("/v1/billing/checkout", response_model=CheckoutOut, dependencies=[Depends(limit("checkout", 10, 3600))])
async def checkout(
    body: CheckoutIn, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> CheckoutOut:
    if get_settings().billing_provider == "manual":
        raise HTTPException(409, "Credits are added by our team. Contact us to top up your workspace.")
    option = credits.option_for(body.amount_usd)
    if option is None:
        raise HTTPException(422, "Choose one of the amounts on offer.")
    co = Checkout(
        workspace_id=p.workspace.id,
        credits=option.credits,
        amount_usd=option.amount_usd,
        provider=get_settings().billing_provider,
    )
    session.add(co)
    await session.flush()
    sess = await registry.get_billing().create_checkout(
        checkout_id=co.id,
        credits=option.credits,
        amount_usd=option.amount_usd,
        description=f"${option.amount_usd:f} of credits ({option.credits} credits)",
    )
    co.provider_ref = sess.provider_ref
    await session.commit()
    return CheckoutOut(checkout_id=co.id, url=sess.url)


async def handle_payment_event(session: AsyncSession, event) -> str:
    """Apply a verified payment event. Idempotent: the ledger `ref` makes a repeated delivery a no-op."""
    co = await session.get(Checkout, event.checkout_id)
    if co is None:
        return "unknown_checkout"
    if event.status != "paid":
        if co.status == "pending":
            co.status = event.status if event.status in {"failed", "expired"} else "failed"
        return "not_paid"
    if event.amount_usd is not None and Decimal(event.amount_usd) != Decimal(co.amount_usd):
        return "amount_mismatch"  # never grant credits for a payment that doesn't match the pack price
    ws = (
        await session.execute(select(Workspace).where(Workspace.id == co.workspace_id).with_for_update())
    ).scalar_one()
    tx = await ledger.apply(
        session,
        ws,
        Decimal(co.credits),
        "purchase",
        ref=f"checkout:{co.id}",
        description=f"Purchased {co.credits} credits",
    )
    if tx is None:
        return "duplicate"
    co.status, co.paid_at = "paid", datetime.now(UTC)
    audit(
        session,
        "billing-webhook",
        "credits.purchased",
        target_type="workspace",
        target_id=ws.id,
        detail={"checkout": co.id, "credits": str(co.credits), "usd": str(co.amount_usd), "event": event.event_id},
    )
    return "granted"


@router.post("/v1/webhooks/billing")
async def billing_webhook(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    body = await request.body()  # the signature is over the RAW body, so read it before any parsing
    try:
        event = registry.get_billing().parse_webhook({k.lower(): v for k, v in request.headers.items()}, body)
    except InvalidSignature:
        raise HTTPException(401, "Invalid signature") from None
    except (KeyError, ValueError):
        raise HTTPException(400, "Malformed event") from None
    result = await handle_payment_event(session, event)
    await session.commit()
    if result == "granted":
        co = await session.get(Checkout, event.checkout_id)
        if co is not None:
            emails = (
                (await session.execute(select(User.email).where(User.workspace_id == co.workspace_id))).scalars().all()
            )
            for to in emails:
                await send_email(
                    to,
                    "Credits added",
                    f"We've added {co.credits} credits to your workspace. Thank you!",
                    link=("Make a video", f"{get_settings().app_base_url}/ai-newsroom/new"),
                )
    return {"result": result}


@router.post("/v1/billing/dev/pay/{checkout_id}")
async def dev_pay(
    checkout_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> dict:
    """Local development only: plays the part of the payment provider by sending our own signed webhook."""
    s = get_settings()
    if not (s.is_local and s.billing_provider == "mock"):
        raise HTTPException(404)
    co = await session.get(Checkout, checkout_id)
    if co is None or co.workspace_id != p.workspace.id:
        raise HTTPException(404)
    provider = registry.get_billing()
    body = json.dumps(
        {"id": f"evt_{checkout_id}", "checkout_id": co.id, "status": "paid", "amount_usd": str(co.amount_usd)}
    ).encode()
    event = provider.parse_webhook({SIGNATURE_HEADER: sign(body, provider.secret)}, body)  # type: ignore[attr-defined]
    result = await handle_payment_event(session, event)
    await session.commit()
    return {"result": result}


@router.get("/v1/billing/ledger", response_model=list[LedgerEntry])
async def ledger_entries(
    limit_: int = 100, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> list[CreditTransaction]:
    rows = await session.execute(
        select(CreditTransaction)
        .where(CreditTransaction.workspace_id == p.workspace.id)
        .order_by(CreditTransaction.created_at.desc(), CreditTransaction.id)
        .limit(min(max(limit_, 1), 500))
    )
    return list(rows.scalars().all())


async def _usage(session: AsyncSession, workspace_id: str, month: str) -> UsageStatement:
    try:
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=UTC)
    except ValueError:
        raise HTTPException(422, "month must look like 2026-10") from None
    end = datetime(start.year + (start.month // 12), start.month % 12 + 1, 1, tzinfo=UTC)
    rows = (
        await session.execute(
            select(CreditTransaction.project_id, CreditTransaction.stage, func.sum(CreditTransaction.amount))
            .where(
                CreditTransaction.workspace_id == workspace_id,
                CreditTransaction.kind.in_(["usage", "usage_adjust", "usage_release"]),
                CreditTransaction.created_at >= start,
                CreditTransaction.created_at < end,
            )
            .group_by(CreditTransaction.project_id, CreditTransaction.stage)
        )
    ).all()
    lines = [UsageLine(project_id=pid, stage=stage, credits=-Decimal(total)) for pid, stage, total in rows if total]
    return UsageStatement(month=month, total_credits=sum((x.credits for x in lines), Decimal("0")), lines=lines)


@router.get("/v1/billing/usage", response_model=UsageStatement)
async def usage(
    month: str | None = None, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> UsageStatement:
    return await _usage(session, p.workspace.id, month or datetime.now(UTC).strftime("%Y-%m"))


@router.get("/v1/billing/usage.csv")
async def usage_csv(
    month: str | None = None, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> Response:
    st = await _usage(session, p.workspace.id, month or datetime.now(UTC).strftime("%Y-%m"))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["month", "project_id", "step", "credits"])
    for ln in st.lines:
        w.writerow([st.month, ln.project_id or "", ln.stage or "", f"{ln.credits:.4f}"])
    w.writerow([st.month, "", "TOTAL", f"{st.total_credits:.4f}"])
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="usage-{st.month}.csv"'},
    )
