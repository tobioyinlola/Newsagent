"""The back-office team: invited with a role or custom permissions, and held to them on the server for every request."""

import re

from sqlalchemy import select

from app.integrations import registry
from app.models import AuditLog, StaffMember, User
from tests.conftest import OPS, OWNER

PW = "correct horse battery"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def mail_to(email):
    return [m for m in registry.get_email().sent if m["to"].lower() == email.lower()]


def token_from_mail(email):
    return re.search(r"token=([\w-]+)", mail_to(email)[-1]["text"]).group(1)


def code_from_mail(email):
    return re.search(r"\b(\d{6})\b", mail_to(email)[-1]["text"]).group(1)


async def invite(client, email, role="support", by=OPS, **extra):
    r = await client.post("/v1/admin/staff", json={"email": email, "role": role, **extra}, headers=by)
    assert r.status_code == 200, r.text
    return r.json()


async def join(client, email, name="New Teammate"):
    """The invited person's side: open the emailed link, choose a password, confirm the emailed code."""
    token = token_from_mail(email)
    pre = await client.post("/v1/auth/staff/invite", json={"token": token})
    assert pre.status_code == 200, pre.text
    r = await client.post("/v1/auth/staff/accept/start", json={"token": token, "password": PW, "name": name})
    assert r.status_code == 200, r.text
    r = await client.post("/v1/auth/staff/accept/verify", json={"token": token, "code": code_from_mail(email)})
    assert r.status_code == 200, r.text
    return bearer(r.json()["token"])


async def test_an_owner_invites_someone_who_joins_and_gets_exactly_their_role(client, workspace):
    out = await invite(client, "sam@cover.example.com", "support", name="Sam")
    assert out["emailed"] and out["join_url"] is None and out["member"]["status"] == "invited"
    assert "Join the team" in mail_to("sam@cover.example.com")[-1]["html"]

    sam = await join(client, "sam@cover.example.com")
    me = (await client.get("/v1/me", headers=sam)).json()
    assert me["is_operator"] and me["staff_role"] == "Support" and not me["is_owner"]
    assert "review.manage" in me["permissions"] and "finance.manage" not in me["permissions"]

    # allowed: what Support does
    assert (await client.get("/v1/admin/overview", headers=sam)).status_code == 200
    assert (await client.get("/v1/admin/queue", headers=sam)).status_code == 200
    assert (await client.get("/v1/admin/moderation", headers=sam)).status_code == 200
    # refused: money, presenter library, the audit log, the team, system switches
    assert (await client.get("/v1/admin/payments", headers=sam)).status_code == 403
    assert (await client.get("/v1/admin/packs", headers=sam)).status_code == 403
    assert (
        await client.post("/v1/admin/packs", json={"name": "x", "credits": "1", "price_usd": "1"}, headers=sam)
    ).status_code == 403
    assert (await client.get("/v1/admin/presenter-clips", headers=sam)).status_code == 403
    assert (await client.get("/v1/admin/audit", headers=sam)).status_code == 403
    assert (await client.get("/v1/admin/staff", headers=sam)).status_code == 403
    assert (await client.patch("/v1/admin/settings", json={}, headers=sam)).status_code == 403
    assert (
        await client.post("/v1/admin/invites", json={"email": "c@x.example.com", "workspace_name": "C"}, headers=sam)
    ).status_code == 403


async def test_joining_is_audited_and_the_link_works_once(client, workspace, maker):
    await invite(client, "once@cover.example.com", "viewer")
    token = token_from_mail("once@cover.example.com")
    await join(client, "once@cover.example.com")
    again = await client.post("/v1/auth/staff/invite", json={"token": token})
    assert again.status_code == 404  # used up
    async with maker() as s:
        actions = [a.action for a in (await s.execute(select(AuditLog))).scalars()]
    assert "staff.invite" in actions and "staff.join" in actions


async def test_a_wrong_code_does_not_join_and_a_bad_link_looks_like_any_other(client, workspace):
    await invite(client, "wrong@cover.example.com", "viewer")
    token = token_from_mail("wrong@cover.example.com")
    await client.post("/v1/auth/staff/accept/start", json={"token": token, "password": PW})
    bad = await client.post("/v1/auth/staff/accept/verify", json={"token": token, "code": "000000"})
    assert bad.status_code == 401
    nope = await client.post("/v1/auth/staff/invite", json={"token": "x" * 30})
    assert nope.status_code == 404
    weak = await client.post("/v1/auth/staff/accept/start", json={"token": token, "password": "short"})
    assert weak.status_code == 422


async def test_a_staff_member_signs_in_with_a_code_each_time_like_any_operator(client, workspace):
    await invite(client, "code@cover.example.com", "viewer")
    await join(client, "code@cover.example.com")
    r = await client.post("/v1/auth/login", json={"email": "code@cover.example.com", "password": PW})
    assert r.status_code == 200 and r.json()["otp_required"] is True
    tok = bearer(r.json()["token"])
    assert (await client.get("/v1/admin/overview", headers=tok)).status_code == 401  # not until the code is entered
    ok = await client.post("/v1/auth/login/otp", json={"code": code_from_mail("code@cover.example.com")}, headers=tok)
    assert ok.status_code == 200
    assert (await client.get("/v1/admin/overview", headers=tok)).status_code == 200


async def test_custom_permissions_are_exactly_what_was_ticked(client, workspace):
    await invite(client, "custom@cover.example.com", "custom", permissions=["finance.view", "overview.view"])
    tok = await join(client, "custom@cover.example.com")
    assert (await client.get("/v1/admin/payments", headers=tok)).status_code == 200
    assert (await client.get("/v1/admin/overview", headers=tok)).status_code == 200
    assert (await client.get("/v1/admin/customers", headers=tok)).status_code == 403
    assert (await client.get("/v1/admin/vendor-budgets", headers=tok)).status_code == 200
    assert (
        await client.put("/v1/admin/vendor-budgets", json={"vendor": "mock", "limit": "5"}, headers=tok)
    ).status_code == 403


async def test_role_changes_take_effect_at_once(client, workspace):
    m = await invite(client, "grow@cover.example.com", "viewer")
    tok = await join(client, "grow@cover.example.com")
    assert (await client.get("/v1/admin/queue", headers=tok)).status_code == 200
    assert (await client.get("/v1/admin/moderation", headers=tok)).status_code == 403
    r = await client.patch(f"/v1/admin/staff/{m['member']['id']}", json={"role": "support"}, headers=OPS)
    assert r.status_code == 200 and r.json()["role_label"] == "Support"
    assert (await client.get("/v1/admin/moderation", headers=tok)).status_code == 200  # same session, new access


async def test_suspend_signs_them_out_everywhere_and_blocks_sign_in_until_restored(client, workspace):
    m = await invite(client, "pause@cover.example.com", "support")
    tok = await join(client, "pause@cover.example.com")
    sid = m["member"]["id"]
    assert (await client.patch(f"/v1/admin/staff/{sid}", json={"status": "suspended"}, headers=OPS)).status_code == 200
    assert (await client.get("/v1/admin/overview", headers=tok)).status_code == 401  # session revoked
    blocked = await client.post("/v1/auth/login", json={"email": "pause@cover.example.com", "password": PW})
    assert blocked.status_code == 401
    assert (await client.patch(f"/v1/admin/staff/{sid}", json={"status": "active"}, headers=OPS)).status_code == 200
    again = await client.post("/v1/auth/login", json={"email": "pause@cover.example.com", "password": PW})
    assert again.status_code == 200


async def test_remove_then_invite_again_restores_a_clean_membership(client, workspace):
    m = await invite(client, "back@cover.example.com", "support")
    tok = await join(client, "back@cover.example.com")
    sid = m["member"]["id"]
    assert (await client.delete(f"/v1/admin/staff/{sid}", headers=OPS)).status_code == 200
    assert (await client.get("/v1/admin/overview", headers=tok)).status_code == 401
    listing = (await client.get("/v1/admin/staff", headers=OPS)).json()
    assert "back@cover.example.com" not in [x["email"] for x in listing["members"]]
    assert (
        await client.post("/v1/auth/login", json={"email": "back@cover.example.com", "password": PW})
    ).status_code == 401
    # asked back, with a different role
    await invite(client, "back@cover.example.com", "finance")
    tok2 = await join(client, "back@cover.example.com")
    me = (await client.get("/v1/me", headers=tok2)).json()
    assert (
        me["staff_role"] == "Finance"
        and "finance.manage" in me["permissions"]
        and "review.manage" not in me["permissions"]
    )


async def test_nobody_can_grant_more_than_they_hold_or_touch_themselves_or_a_senior(client, workspace):
    # an admin who manages the team but has no finance.manage
    await invite(
        client, "lead@cover.example.com", "custom", permissions=["team.manage", "overview.view", "customers.view"]
    )
    lead = await join(client, "lead@cover.example.com")

    over = await client.post("/v1/admin/staff", json={"email": "up@cover.example.com", "role": "finance"}, headers=lead)
    assert over.status_code == 403  # finance.manage is beyond them
    over = await client.post(
        "/v1/admin/staff",
        json={"email": "up@cover.example.com", "role": "custom", "permissions": ["audit.view"]},
        headers=lead,
    )
    assert over.status_code == 403
    fine = await client.post(
        "/v1/admin/staff",
        json={"email": "ok@cover.example.com", "role": "custom", "permissions": ["customers.view"]},
        headers=lead,
    )
    assert fine.status_code == 200

    team = (await client.get("/v1/admin/staff", headers=lead)).json()
    me = next(x for x in team["members"] if x["email"] == "lead@cover.example.com")
    assert me["is_you"] and not me["editable"]
    assert (await client.patch(f"/v1/admin/staff/{me['id']}", json={"role": "admin"}, headers=lead)).status_code == 409
    assert (await client.delete(f"/v1/admin/staff/{me['id']}", headers=lead)).status_code == 409

    # a finance person holds finance.manage, which the lead lacks: the lead can't edit or remove them
    fin = await invite(client, "money@cover.example.com", "finance")
    assert (
        await client.patch(f"/v1/admin/staff/{fin['member']['id']}", json={"role": "viewer"}, headers=lead)
    ).status_code == 403
    assert (await client.delete(f"/v1/admin/staff/{fin['member']['id']}", headers=lead)).status_code == 403
    row = next(
        x
        for x in (await client.get("/v1/admin/staff", headers=lead)).json()["members"]
        if x["email"] == "money@cover.example.com"
    )
    assert not row["editable"]


async def test_owners_are_listed_but_cannot_be_invited_or_changed(client, workspace):
    team = (await client.get("/v1/admin/staff", headers=OPS)).json()
    owner = next(x for x in team["members"] if x["status"] == "owner")
    assert owner["email"] == "ops@example.com" and not owner["editable"] and owner["role_label"] == "Owner"
    r = await client.post("/v1/admin/staff", json={"email": "ops@example.com", "role": "viewer"}, headers=OPS)
    assert r.status_code == 409
    assert (
        await client.patch(f"/v1/admin/staff/{owner['id']}", json={"role": "viewer"}, headers=OPS)
    ).status_code == 404


async def test_customers_cannot_use_any_of_it_and_cannot_be_invited_to_the_team(client, workspace):
    for call in (
        client.get("/v1/admin/staff", headers=OWNER),
        client.post("/v1/admin/staff", json={"email": "x@y.example.com", "role": "viewer"}, headers=OWNER),
        client.get("/v1/admin/overview", headers=OWNER),
    ):
        assert (await call).status_code == 403
    # an existing customer account can't be turned into staff by an invitation
    from tests.test_auth_flow import NEW, signup

    await signup(client)
    r = await client.post("/v1/admin/staff", json={"email": NEW, "role": "viewer"}, headers=OPS)
    assert r.status_code == 409


async def test_bad_roles_and_permissions_are_rejected(client, workspace):
    bad = await client.post("/v1/admin/staff", json={"email": "a@b.example.com", "role": "wizard"}, headers=OPS)
    assert bad.status_code == 422
    bad = await client.post(
        "/v1/admin/staff", json={"email": "a@b.example.com", "role": "custom", "permissions": ["nope"]}, headers=OPS
    )
    assert bad.status_code == 422
    bad = await client.post(
        "/v1/admin/staff", json={"email": "a@b.example.com", "role": "custom", "permissions": []}, headers=OPS
    )
    assert bad.status_code == 422
    dup = await invite(client, "dup@cover.example.com", "viewer")
    await join(client, "dup@cover.example.com")
    again = await client.post("/v1/admin/staff", json={"email": "dup@cover.example.com", "role": "viewer"}, headers=OPS)
    assert again.status_code == 409 and dup


async def test_resend_replaces_the_link_and_an_expired_one_is_refused(client, workspace, maker):
    m = await invite(client, "late@cover.example.com", "viewer")
    old = token_from_mail("late@cover.example.com")
    r = await client.post(f"/v1/admin/staff/{m['member']['id']}/resend", headers=OPS)
    assert r.status_code == 200 and r.json()["emailed"]
    new = token_from_mail("late@cover.example.com")
    assert new != old
    assert (await client.post("/v1/auth/staff/invite", json={"token": old})).status_code == 404
    from datetime import UTC, datetime, timedelta

    async with maker() as s:
        row = (await s.execute(select(StaffMember).where(StaffMember.email == "late@cover.example.com"))).scalar_one()
        row.invite_expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()
    assert (await client.post("/v1/auth/staff/invite", json={"token": new})).status_code == 404


async def test_the_team_is_not_counted_as_a_customer(client, workspace, maker):
    await invite(client, "intern@cover.example.com", "viewer")
    await join(client, "intern@cover.example.com")
    emails = [c["owner_email"] for c in (await client.get("/v1/admin/customers", headers=OPS)).json()["items"]]
    assert "intern@cover.example.com" not in emails
    async with maker() as s:
        user = (await s.execute(select(User).where(User.email == "intern@cover.example.com"))).scalar_one()
        assert user.role == "staff"


async def test_when_email_cannot_be_sent_the_inviter_gets_the_link(client, workspace, monkeypatch):
    from app.routes import staff

    async def failing(*a, **k):
        return False

    monkeypatch.setattr(staff, "send_email", failing)
    r = await invite(client, "nomail@cover.example.com", "viewer")
    assert r["emailed"] is False and "/admin/join?token=" in r["join_url"]
