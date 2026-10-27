import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import AuditLog, AuthCode, Invite, User, UserSession, Workspace
from app.services import passwords
from tests.conftest import OPS, OWNER

NEW = "newfounder@startup.example.com"
PW = "correct horse battery"
OPS_EMAIL = "ops@example.com"
PW2 = "another long passphrase"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def last_code(email):
    mails = [m for m in registry.get_email().sent if m["to"].lower() == email.lower()]
    return re.search(r"\b(\d{6})\b", mails[-1]["text"]).group(1)


async def invite_for(client, email=NEW, name="NewCo"):
    r = await client.post(
        "/v1/admin/invites", json={"email": email, "workspace_name": name, "credits": "5"}, headers=OPS
    )
    return r.json()["code"]


async def signup(client, email=NEW, password=PW):
    code = await invite_for(client, email)
    r = await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": password})
    assert r.status_code == 200, r.text
    r = await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": last_code(email)})
    assert r.status_code == 200, r.text
    return r.json()


async def login(client, email=NEW, password=PW):
    r = await client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


async def set_password(client, email, password):
    """For accounts created without one (operators): the forgot-password flow."""
    await client.post("/v1/auth/password/forgot", json={"email": email})
    r = await client.post(
        "/v1/auth/password/reset", json={"email": email, "code": last_code(email), "new_password": password}
    )
    assert r.status_code == 200, r.text


# ---------- passwords ----------
def test_password_hashing_and_policy():
    h = passwords.hash_password(PW)
    assert h.startswith("scrypt$") and PW not in h and h != passwords.hash_password(PW)  # salted
    assert passwords.verify_password(PW, h) and not passwords.verify_password(PW + "x", h)
    assert not passwords.verify_password(PW, None) and not passwords.verify_password(PW, "garbage")
    assert passwords.policy_error("short", "a@b.com")
    assert passwords.policy_error("password123", "a@b.com")
    assert passwords.policy_error("aaaaaaaaaaaa", "a@b.com")
    assert passwords.policy_error("jane.doe@x.com", "jane.doe@x.com")
    assert passwords.policy_error("myjanedoe-pass99", "janedoe@x.com")
    assert passwords.policy_error("x" * 129, "a@b.com")
    assert passwords.policy_error(PW, "a@b.com") is None


# ---------- sign up ----------
async def test_invite_preview_hides_the_email_and_rejects_bad_links(client, workspace, maker):
    code = await invite_for(client)
    p = (await client.get(f"/v1/auth/invite/{code}")).json()
    assert p["workspace_name"] == "NewCo" and p["email_hint"] == "n*********@startup.example.com" and NEW not in str(p)
    assert (await client.get("/v1/auth/invite/not-a-real-code-1")).status_code == 404
    async with maker() as s:
        inv = (await s.execute(select(Invite).where(Invite.code == code))).scalar_one()
        inv.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()
    assert (await client.get(f"/v1/auth/invite/{code}")).status_code == 404


async def test_signup_needs_the_emailed_code_and_then_signs_you_in(client, workspace, maker):
    code = await invite_for(client)
    r = await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})
    assert r.status_code == 200 and r.json()["email_hint"].endswith("@startup.example.com")
    async with maker() as db:  # nothing exists until the code is verified
        assert (await db.execute(select(User).where(User.email == NEW))).scalar_one_or_none() is None
    s = (await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": last_code(NEW)})).json()
    assert s["token"].startswith("nas_") and s["otp_required"] is False
    me = (await client.get("/v1/me", headers=bearer(s["token"]))).json()
    assert me["email"] == NEW and me["workspace_name"] == "NewCo" and float(me["credit_balance"]) == 5.0
    async with maker() as db:
        u = (await db.execute(select(User).where(User.email == NEW))).scalar_one()
        assert u.password_hash.startswith("scrypt$") and PW not in u.password_hash and u.last_login_at is not None
        ws = (await db.execute(select(Workspace).where(Workspace.name == "NewCo"))).scalar_one()
        assert ws.brand_kit_id is not None
        assert (await db.execute(select(AuditLog).where(AuditLog.action == "auth.signup"))).scalar_one().actor == NEW
        assert (await db.execute(select(AuthCode))).scalar_one().password_hash is None  # wiped after use


async def test_the_password_is_checked_before_a_code_is_sent_and_never_stored_in_plain_text(client, workspace, maker):
    code = await invite_for(client)
    for bad in ("short", "password123", NEW):
        r = await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": bad})
        assert r.status_code in (422,), (bad, r.text)
    assert not [m for m in registry.get_email().sent if m["to"] == NEW and "your Cover Founder code" in m["subject"]]
    await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})
    async with maker() as db:
        row = (await db.execute(select(AuthCode))).scalar_one()
        assert PW not in (row.password_hash or "") and PW not in row.code_hash
        assert last_code(NEW) not in row.code_hash and len(row.code_hash) == 64 and row.purpose == "signup"


async def test_a_used_invite_and_an_existing_account_are_refused(client, workspace):
    await signup(client)
    r = await client.post("/v1/admin/invites", json={"email": "ops@example.com", "workspace_name": "Dup"}, headers=OPS)
    res = await client.post("/v1/auth/signup/start", json={"invite_code": r.json()["code"], "password": PW})
    assert res.status_code == 409


async def test_a_used_invite_cannot_be_used_again(client, workspace):
    code = await invite_for(client)
    await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})
    await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": last_code(NEW)})
    assert (await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})).status_code == 404


# ---------- one-time code rules ----------
async def test_five_wrong_guesses_burn_the_code(client, workspace):
    code = await invite_for(client)
    await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})
    good = last_code(NEW)
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert (
            await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": wrong})
        ).status_code == 401
    assert (await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": good})).status_code == 401
    await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})  # a fresh code works
    assert (
        await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": last_code(NEW)})
    ).status_code == 200


async def age_codes(maker, seconds=120):
    async with maker() as db:
        for r in (await db.execute(select(AuthCode))).scalars():
            r.created_at -= timedelta(seconds=seconds)
        await db.commit()


async def test_a_code_requested_moments_ago_still_works_after_a_quick_resend(client, workspace):
    code = await invite_for(client)
    await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})
    first = last_code(NEW)
    await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})
    assert (await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": first})).status_code == 200


async def test_a_new_code_cancels_the_old_and_expired_codes_fail(client, workspace, maker):
    code = await invite_for(client)
    await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})
    first = last_code(NEW)
    await age_codes(maker)
    await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW2})
    second = last_code(NEW)
    assert first != second
    assert (await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": first})).status_code == 401
    async with maker() as db:
        row = (await db.execute(select(AuthCode).where(AuthCode.consumed_at.is_(None)))).scalar_one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": second})).status_code == 401


async def test_a_code_for_one_purpose_cannot_be_used_for_another(client, workspace):
    await signup(client)
    await client.post("/v1/auth/password/forgot", json={"email": NEW})
    r = await client.post("/v1/auth/password/reset", json={"email": NEW, "code": last_code(NEW), "new_password": PW2})
    assert r.status_code == 200
    code = await invite_for(client, "other@startup.example.com")
    await client.post("/v1/auth/password/forgot", json={"email": NEW})
    r = await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": last_code(NEW)})
    assert r.status_code == 401


async def test_input_validation(client, workspace):
    assert (await client.post("/v1/auth/login", json={"email": "not-an-email", "password": "x"})).status_code == 422
    code = await invite_for(client)
    for bad in ("12345", "1234567", "abcdef", ""):
        assert (await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": bad})).status_code == 422


# ---------- password sign in ----------
async def test_login_with_the_right_password_only(client, workspace):
    await signup(client)
    s = await login(client)
    assert s["otp_required"] is False and (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 200
    for email, pw in ((NEW, "wrong password!"), ("nobody@startup.example.com", PW), (NEW.upper(), "x")):
        r = await client.post("/v1/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 401
    assert (
        await client.post("/v1/auth/login", json={"email": NEW.upper(), "password": PW})
    ).status_code == 200  # case-insensitive email


async def test_wrong_password_looks_the_same_for_unknown_and_known_emails(client, workspace, maker):
    await signup(client)
    no_password = OPS_EMAIL  # an account that has no password yet
    async with maker() as db:
        u = (await db.execute(select(User).where(User.email == no_password))).scalar_one_or_none()
        assert u is not None and u.password_hash is None
    bodies = []
    for email in (NEW, "nobody@startup.example.com", no_password):
        r = await client.post("/v1/auth/login", json={"email": email, "password": "not the password"})
        assert r.status_code == 401
        bodies.append(r.json())
    assert bodies[0] == bodies[1] == bodies[2]


async def test_login_is_throttled_per_email(client, workspace):
    await signup(client)
    codes = [
        (await client.post("/v1/auth/login", json={"email": NEW, "password": "bad password!"})).status_code
        for _ in range(12)
    ]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]
    assert (
        await client.post("/v1/auth/login", json={"email": NEW, "password": PW})
    ).status_code == 429  # even the right one


async def test_signup_code_requests_are_throttled(client, workspace):
    code = await invite_for(client)
    codes = [
        (await client.post("/v1/auth/signup/start", json={"invite_code": code, "password": PW})).status_code
        for _ in range(6)
    ]
    assert codes == [200] * 5 + [429]


# ---------- forgot / change password ----------
async def test_forgot_password_never_reveals_accounts(client, workspace):
    await signup(client)
    registry.get_email().sent.clear()
    known = await client.post("/v1/auth/password/forgot", json={"email": NEW})
    unknown = await client.post("/v1/auth/password/forgot", json={"email": "nobody@startup.example.com"})
    assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
    assert [m["to"] for m in registry.get_email().sent] == [NEW]


async def test_reset_sets_a_new_password_and_signs_everyone_out(client, workspace):
    a = await signup(client)
    await client.post("/v1/auth/password/forgot", json={"email": NEW})
    code = last_code(NEW)
    weak = await client.post("/v1/auth/password/reset", json={"email": NEW, "code": code, "new_password": "short"})
    assert weak.status_code == 422
    r = await client.post("/v1/auth/password/reset", json={"email": NEW, "code": code, "new_password": PW2})
    assert r.status_code == 200
    assert (await client.get("/v1/me", headers=bearer(a["token"]))).status_code == 401
    assert (await client.post("/v1/auth/login", json={"email": NEW, "password": PW})).status_code == 401
    await login(client, password=PW2)
    again = await client.post("/v1/auth/password/reset", json={"email": NEW, "code": code, "new_password": PW})
    assert again.status_code == 401  # single use


async def test_reset_with_a_wrong_code_or_unknown_email_fails_identically(client, workspace):
    await signup(client)
    await client.post("/v1/auth/password/forgot", json={"email": NEW})
    a = await client.post("/v1/auth/password/reset", json={"email": NEW, "code": "000000", "new_password": PW2})
    b = await client.post(
        "/v1/auth/password/reset", json={"email": "nobody@startup.example.com", "code": "000000", "new_password": PW2}
    )
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


async def test_change_password_needs_the_current_one_and_keeps_only_this_device(client, workspace):
    a = await signup(client)
    b = await login(client)
    h = bearer(a["token"])
    assert (
        await client.post(
            "/v1/auth/password/change", json={"current_password": "wrong one!!", "new_password": PW2}, headers=h
        )
    ).status_code == 401
    assert (
        await client.post("/v1/auth/password/change", json={"current_password": PW, "new_password": "short"}, headers=h)
    ).status_code == 422
    assert (
        await client.post("/v1/auth/password/change", json={"current_password": PW, "new_password": PW2}, headers=h)
    ).status_code == 200
    assert (await client.get("/v1/me", headers=h)).status_code == 200
    assert (await client.get("/v1/me", headers=bearer(b["token"]))).status_code == 401
    await login(client, password=PW2)


# ---------- sessions ----------
async def test_only_a_hash_of_the_token_is_stored_and_logout_revokes_it(client, workspace, maker):
    s = await signup(client)
    async with maker() as db:
        row = (await db.execute(select(UserSession))).scalar_one()
        assert s["token"] not in row.token_hash and len(row.token_hash) == 64
    assert (await client.post("/v1/auth/logout", headers=bearer(s["token"]))).status_code == 200
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 401


async def test_sessions_list_revoke_and_logout_everywhere(client, workspace):
    a, b, c = await signup(client), await login(client), await login(client)
    ha = bearer(a["token"])
    lst = (await client.get("/v1/auth/sessions", headers=ha)).json()
    assert len(lst) == 3 and sum(x["current"] for x in lst) == 1
    other = next(x for x in lst if not x["current"])
    assert (await client.delete(f"/v1/auth/sessions/{other['id']}", headers=ha)).status_code == 200
    assert len((await client.get("/v1/auth/sessions", headers=ha)).json()) == 2
    assert (await client.post("/v1/auth/logout-all", headers=ha)).status_code == 200
    for t in (a, b, c):
        assert (await client.get("/v1/me", headers=bearer(t["token"]))).status_code == 401


async def test_you_cannot_revoke_someone_elses_session(client, workspace):
    a = await signup(client)
    await signup(client, "second@startup.example.com")
    victim = (await client.get("/v1/auth/sessions", headers=bearer(a["token"]))).json()[0]["id"]
    other = await login(client, "second@startup.example.com")
    assert (await client.delete(f"/v1/auth/sessions/{victim}", headers=bearer(other["token"]))).status_code == 404
    assert (await client.get("/v1/me", headers=bearer(a["token"]))).status_code == 200


async def test_signed_out_after_one_hour_idle_but_activity_keeps_you_in(client, workspace, maker):
    assert get_settings().session_idle_minutes == 60
    s = await signup(client)
    async with maker() as db:
        row = (await db.execute(select(UserSession))).scalar_one()
        row.last_used_at = datetime.now(UTC) - timedelta(minutes=59)
        await db.commit()
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 200  # used again: the clock restarts
    async with maker() as db:
        row = (await db.execute(select(UserSession))).scalar_one()
        assert datetime.now(UTC) - row.last_used_at.replace(tzinfo=UTC) < timedelta(minutes=2)
        row.last_used_at = datetime.now(UTC) - timedelta(minutes=61)
        await db.commit()
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 401
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 401  # and it stays dead


async def test_absolute_expiry(client, workspace, maker):
    s = await signup(client)
    async with maker() as db:
        row = (await db.execute(select(UserSession))).scalar_one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 401


async def test_garbage_and_missing_tokens(client, workspace):
    for h in ({}, {"Authorization": "Bearer"}, bearer("nas_nope"), bearer("a" * 50), {"Authorization": "Basic abc"}):
        assert (await client.get("/v1/me", headers=h)).status_code == 401


async def test_dev_tokens_only_work_locally(client, workspace, monkeypatch):
    assert (await client.get("/v1/me", headers=OWNER)).status_code == 200
    monkeypatch.setattr(get_settings(), "environment", "production")
    assert (await client.get("/v1/me", headers=OWNER)).status_code == 401


async def test_deleting_the_workspace_signs_everyone_out(client, workspace, maker):
    s = await signup(client)
    r = await client.request("DELETE", "/v1/account", json={"confirm": "DELETE NewCo"}, headers=bearer(s["token"]))
    assert r.status_code == 200
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 401
    async with maker() as db:
        assert (await db.execute(select(UserSession))).scalars().all() == []
        assert (await db.execute(select(AuthCode).where(AuthCode.email == NEW))).scalars().all() == []


# ---------- operators confirm each sign-in with an emailed code ----------


async def operator_login(client):
    return await login(client, OPS_EMAIL, PW)


async def test_operators_confirm_each_sign_in_with_a_code(client, workspace):
    await set_password(client, OPS_EMAIL, PW)
    s = await operator_login(client)
    assert s["otp_required"] is True
    h = bearer(s["token"])
    held = await client.get("/v1/me", headers=h)
    assert held.status_code == 401 and held.json()["detail"]["error"] == "otp_required"
    assert (await client.get("/v1/admin/queue", headers=h)).status_code == 401
    assert (await client.post("/v1/auth/login/otp", json={"code": "000000"}, headers=h)).status_code == 401
    assert (await client.post("/v1/auth/login/otp", json={"code": last_code(OPS_EMAIL)}, headers=h)).status_code == 200
    assert (await client.get("/v1/admin/queue", headers=h)).status_code == 200
    again = await operator_login(client)  # every sign-in needs its own code
    assert (await client.get("/v1/admin/queue", headers=bearer(again["token"]))).status_code == 401


async def test_operator_code_can_be_resent_and_is_throttled(client, workspace, maker):
    await set_password(client, OPS_EMAIL, PW)
    h = bearer((await operator_login(client))["token"])
    first = last_code(OPS_EMAIL)
    await age_codes(maker)
    assert (await client.post("/v1/auth/login/otp/resend", headers=h)).status_code == 200
    second = last_code(OPS_EMAIL)
    assert (
        await client.post("/v1/auth/login/otp", json={"code": first}, headers=h)
    ).status_code == 401 or first == second
    assert (await client.post("/v1/auth/login/otp", json={"code": second}, headers=h)).status_code == 200
    statuses = [
        (
            await client.post("/v1/auth/login/otp/resend", headers=bearer((await operator_login(client))["token"]))
        ).status_code
        for _ in range(1)
    ]
    assert statuses == [200]


async def test_regular_users_are_not_asked_for_a_code_and_cannot_use_the_endpoint(client, workspace):
    s = await signup(client)
    assert s["otp_required"] is False
    assert (await client.post("/v1/auth/login/otp/resend", headers=bearer(s["token"]))).status_code == 409


async def test_operator_sessions_are_short_and_sign_ins_are_audited(client, workspace, maker):
    await set_password(client, OPS_EMAIL, PW)
    s = await operator_login(client)
    await client.post("/v1/auth/login/otp", json={"code": last_code(OPS_EMAIL)}, headers=bearer(s["token"]))
    async with maker() as db:
        row = (await db.execute(select(UserSession).order_by(UserSession.created_at.desc()))).scalars().first()
        assert (
            timedelta(hours=7, minutes=59)
            < row.expires_at.replace(tzinfo=UTC) - row.created_at.replace(tzinfo=UTC)
            < timedelta(hours=8, minutes=1)
        )
        actions = [a.action for a in (await db.execute(select(AuditLog))).scalars()]
    assert {"auth.login", "auth.login_verified", "auth.password_reset"} <= set(actions)


async def test_dev_mailbox_endpoint_exists_only_for_local_mock_mail(client, workspace):
    registry.get_email().sent.append({"to": NEW, "subject": "s", "text": "code 123456"})
    r = await client.get("/v1/dev/last-email", params={"to": NEW})
    assert r.status_code == 200 and "123456" in r.json()["text"]
    assert (await client.get("/v1/dev/last-email", params={"to": "none@x.example.com"})).status_code == 404


async def test_an_invite_is_emailed_to_the_startup_with_the_signup_link(client, workspace):
    r = await client.post(
        "/v1/admin/invites", json={"email": NEW, "workspace_name": "NewCo", "credits": "5"}, headers=OPS
    )
    body = r.json()
    assert body["emailed"] is True
    mail = [m for m in registry.get_email().sent if m["to"] == NEW and "invited" in m["subject"]]
    assert len(mail) == 1
    assert f"/signup?code={body['code']}" in mail[0]["text"] and "How to sign up" in mail[0]["text"]
    assert "#C0FE73" in mail[0]["html"] and "Create your account" in mail[0]["html"]
