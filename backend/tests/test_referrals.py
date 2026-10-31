import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import AuthCode, CreditTransaction, ReferralLink, ReferralReward, User, Workspace
from app.services import ledger, referrals
from app.services.privacy import delete_workspace, export_workspace
from tests.conftest import OWNER
from tests.test_auth_flow import PW, last_code


async def link(client, headers=OWNER):
    r = await client.get("/v1/referrals", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def begin(client, email, code=None):
    body = {
        "email": email,
        "business_name": "Referred Business",
        "city": "Lagos",
        "country": "Nigeria",
        "industry": "technology",
        "password": PW,
    }
    if code is not None:
        body["referral_code"] = code
    r = await client.post("/v1/auth/signup/start", json=body)
    assert r.status_code == 200, r.text
    return {"email": email, "code": last_code(email)}


async def balance(maker, workspace):
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        assert await ledger.ledger_sum(db, workspace) == ws.credit_balance
        return ws.credit_balance


async def test_link_is_unique_stable_and_user_scoped(client, workspace, maker):
    a = await link(client)
    assert (await link(client))["url"] == a["url"]
    assert len(a["code"]) == 24 and a["url"].endswith("/signup?ref=" + a["code"])
    b = await link(client, {"Authorization": "Bearer dev:ops@example.com"})
    assert b["code"] != a["code"]
    assert a["completed_referrals"] == 0 and Decimal(a["earned_credits"]) == 0
    assert (await client.get("/v1/referrals")).status_code == 401
    assert await balance(maker, workspace) == 10


async def test_verified_signup_credits_once_and_allocates_new_link(client, workspace, maker):
    a = await link(client)
    verify = await begin(client, "referral-new@example.com", a["code"])
    assert await balance(maker, workspace) == 10
    wrong = await client.post("/v1/auth/signup/verify", json={**verify, "code": "not-six"})
    assert wrong.status_code == 422
    async with maker() as db:
        assert (await db.execute(select(func.count(ReferralReward.id)))).scalar_one() == 0
    result = await client.post("/v1/auth/signup/verify", json=verify)
    assert result.status_code == 200, result.text
    assert await balance(maker, workspace) == 11
    repeated = await client.post("/v1/auth/signup/verify", json=verify)
    assert repeated.status_code in {401, 409}
    assert await balance(maker, workspace) == 11
    report = await link(client)
    assert report["completed_referrals"] == 1 and Decimal(report["earned_credits"]) == 1
    assert report["referrals"][0]["business"] == "Referred Business"
    assert "email" not in report["referrals"][0]
    own = await link(client, {"Authorization": "Bearer " + result.json()["token"]})
    assert own["code"] != a["code"] and own["completed_referrals"] == 0
    async with maker() as db:
        user = (await db.execute(select(User).where(User.email == verify["email"]))).scalar_one()
        assert (await db.execute(select(ReferralLink).where(ReferralLink.user_id == user.id))).scalar_one()
        assert await referrals.reward(db, a["code"], user) is False
        tx = (
            await db.execute(select(CreditTransaction).where(CreditTransaction.ref == f"referral:{user.workspace_id}"))
        ).scalar_one()
        assert tx.amount == 1 and tx.kind == "grant"


@pytest.mark.parametrize("code", [None, "invalid", "A" * 24])
async def test_missing_or_invalid_link_does_not_block_signup_or_credit(client, workspace, maker, code):
    verify = await begin(client, "no-referral@example.com", code)
    r = await client.post("/v1/auth/signup/verify", json=verify)
    assert r.status_code == 200, r.text
    assert await balance(maker, workspace) == 10


async def test_referral_is_bound_to_verified_code_not_verify_payload(client, workspace, maker):
    owner = await link(client)
    other = await link(client, {"Authorization": "Bearer dev:ops@example.com"})
    body = await begin(client, "bound-referral@example.com", owner["code"])
    r = await client.post("/v1/auth/signup/verify", json={**body, "referral_code": other["code"]})
    assert r.status_code == 200, r.text
    assert (await link(client))["completed_referrals"] == 1
    assert (await link(client, {"Authorization": "Bearer dev:ops@example.com"}))["completed_referrals"] == 0
    assert await balance(maker, workspace) == 11


async def test_resend_and_expired_codes_never_award_early(client, workspace, maker):
    a = await link(client)
    old = await begin(client, "resend-referral@example.com", a["code"])
    async with maker() as db:
        for row in (await db.execute(select(AuthCode).where(AuthCode.email == old["email"]))).scalars():
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await db.commit()
    assert (await client.post("/v1/auth/signup/verify", json=old)).status_code == 401
    assert await balance(maker, workspace) == 10
    fresh = await begin(client, old["email"], a["code"])
    assert (await client.post("/v1/auth/signup/verify", json=fresh)).status_code == 200
    assert await balance(maker, workspace) == 11


async def test_existing_account_self_referral_and_workspace_invite_do_not_reward(client, workspace, maker):
    from tests.test_auth_flow import invite_for

    a = await link(client)
    r = await client.post(
        "/v1/auth/signup/start",
        json={
            "email": "ops@example.com",
            "business_name": "Self",
            "city": "Lagos",
            "country": "Nigeria",
            "industry": "technology",
            "password": PW,
            "referral_code": a["code"],
        },
    )
    assert r.status_code == 409
    code = await invite_for(client, "invited-referral@example.com")
    r = await client.post(
        "/v1/auth/signup/start", json={"invite_code": code, "password": PW, "referral_code": a["code"]}
    )
    assert r.status_code == 200
    r = await client.post(
        "/v1/auth/signup/verify", json={"invite_code": code, "code": last_code("invited-referral@example.com")}
    )
    assert r.status_code == 200, r.text
    async with maker() as db:
        user = (await db.execute(select(User).where(User.email == "owner@acme.test"))).scalar_one()
        assert not await referrals.reward(db, a["code"], user)
    assert await balance(maker, workspace) == 10
    assert (await link(client))["completed_referrals"] == 0


async def test_two_parallel_signups_do_not_lose_a_reward(client, workspace, maker):
    a = await link(client)
    one = await begin(client, "parallel-one@example.com", a["code"])
    two = await begin(client, "parallel-two@example.com", a["code"])
    results = await asyncio.gather(
        client.post("/v1/auth/signup/verify", json=one), client.post("/v1/auth/signup/verify", json=two)
    )
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert await balance(maker, workspace) == 12
    assert (await link(client))["completed_referrals"] == 2


async def test_parallel_duplicate_verification_rewards_only_once(client, workspace, maker):
    a = await link(client)
    body = await begin(client, "parallel-duplicate@example.com", a["code"])
    results = await asyncio.gather(
        client.post("/v1/auth/signup/verify", json=body), client.post("/v1/auth/signup/verify", json=body)
    )
    assert sorted(r.status_code for r in results) == [200, 401], [r.text for r in results]
    assert await balance(maker, workspace) == 11


async def test_inactive_referrer_does_not_break_signup(client, workspace, maker):
    a = await link(client)
    verify = await begin(client, "inactive-referral@example.com", a["code"])
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        ws.suspended = True
        await db.commit()
    assert (await client.post("/v1/auth/signup/verify", json=verify)).status_code == 200
    assert await balance(maker, workspace) == 10


async def test_referral_privacy_export_and_deletion(client, workspace, maker):
    a = await link(client)
    verify = await begin(client, "privacy-referral@example.com", a["code"])
    assert (await client.post("/v1/auth/signup/verify", json=verify)).status_code == 200
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        owner = (await db.execute(select(User).where(User.email == "owner@acme.test"))).scalar_one()
        data = await export_workspace(db, ws, owner)
        assert data["referrals"][0]["direction"] == "invited"
        await delete_workspace(db, ws)
        await db.commit()
        assert (
            not (await db.execute(select(ReferralLink))).scalars().all()
            or not (await db.execute(select(ReferralLink).where(ReferralLink.code == a["code"]))).first()
        )
        reward = (await db.execute(select(ReferralReward))).scalar_one()
        assert reward.referrer_user_id is None
        assert await referrals.resolve(db, a["code"]) is None
