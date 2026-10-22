import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.cli import reset_mfa
from app.config import get_settings
from app.integrations import registry
from app.models import AuditLog, AuthCode, Invite, RecoveryCode, User, UserSession, Workspace
from app.services import totp
from tests.conftest import OPS, OWNER

NEW = "newfounder@startup.example.com"


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


async def signup(client, email=NEW):
    code = await invite_for(client, email)
    assert (await client.post("/v1/auth/signup/start", json={"invite_code": code})).status_code == 200
    r = await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": last_code(email)})
    assert r.status_code == 200, r.text
    return r.json()


async def login(client, email=NEW):
    assert (await client.post("/v1/auth/login/start", json={"email": email})).status_code == 200
    r = await client.post("/v1/auth/login/verify", json={"email": email, "code": last_code(email)})
    assert r.status_code == 200, r.text
    return r.json()


def now_code(secret, offset=0):
    return totp._code(secret, int(datetime.now(UTC).timestamp() // 30) + offset)


# ---------- TOTP ----------
def test_totp_matches_rfc6238_vectors():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # ASCII "12345678901234567890"
    assert totp._code(secret, 59 // 30) == "287082"
    assert totp._code(secret, 1111111109 // 30) == "081804"
    assert totp.verify(secret, "287082", now=59) == 1


def test_totp_window_replay_and_junk():
    s = totp.new_secret()
    t = 1_700_000_000.0
    step = int(t // 30)
    assert totp.verify(s, totp._code(s, step - 1), now=t) == step - 1  # one step of clock drift is fine
    assert totp.verify(s, totp._code(s, step - 3), now=t) is None
    assert totp.verify(s, totp._code(s, step), last_step=step, now=t) is None  # replay of a used code
    assert totp.verify(s, "12345", now=t) is None and totp.verify(s, "abcdef", now=t) is None
    assert totp.provisioning_uri(s, "a@b.com").startswith("otpauth://totp/Newsagent:a%40b.com?secret=")


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


async def test_signup_proves_control_of_the_invited_email_and_signs_you_in(client, workspace, maker):
    s = await signup(client)
    assert s["token"].startswith("nas_") and s["mfa_required"] is False and s["mfa_enrolment_required"] is False
    me = (await client.get("/v1/me", headers=bearer(s["token"]))).json()
    assert me["email"] == NEW and me["workspace_name"] == "NewCo" and float(me["credit_balance"]) == 5.0
    async with maker() as db:
        assert (await db.execute(select(User).where(User.email == NEW))).scalar_one().last_login_at is not None
        ws = (await db.execute(select(Workspace).where(Workspace.name == "NewCo"))).scalar_one()
        assert ws.brand_kit_id is not None
        assert (await db.execute(select(AuditLog).where(AuditLog.action == "auth.signup"))).scalar_one().actor == NEW


async def test_a_used_invite_and_an_existing_account_are_refused(client, workspace):
    code = await invite_for(client)
    await client.post("/v1/auth/signup/start", json={"invite_code": code})
    await client.post("/v1/auth/signup/verify", json={"invite_code": code, "code": last_code(NEW)})
    assert (await client.post("/v1/auth/signup/start", json={"invite_code": code})).status_code == 404  # already used
    dup = await invite_for(
        client, "owner@acme.example.com"
    )  # other invite, but give it an email that already has an account
    from app.models import User as U  # noqa: F401

    r = await client.post("/v1/admin/invites", json={"email": "ops@example.com", "workspace_name": "Dup"}, headers=OPS)
    assert (await client.post("/v1/auth/signup/start", json={"invite_code": r.json()["code"]})).status_code == 409
    assert dup


async def test_codes_are_not_stored_in_plain_text(client, workspace, maker):
    code = await invite_for(client)
    await client.post("/v1/auth/signup/start", json={"invite_code": code})
    plain = last_code(NEW)
    async with maker() as db:
        row = (await db.execute(select(AuthCode))).scalar_one()
        assert plain not in row.code_hash and len(row.code_hash) == 64 and row.purpose == "signup"


# ---------- one-time code rules ----------
async def test_five_wrong_guesses_burn_the_code_even_for_the_right_answer(client, workspace):
    await signup(client)
    await client.post("/v1/auth/login/start", json={"email": NEW})
    good = last_code(NEW)
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(5):
        assert (await client.post("/v1/auth/login/verify", json={"email": NEW, "code": wrong})).status_code == 401
    assert (await client.post("/v1/auth/login/verify", json={"email": NEW, "code": good})).status_code == 401  # burned
    await client.post("/v1/auth/login/start", json={"email": NEW})  # a fresh code works
    assert (await client.post("/v1/auth/login/verify", json={"email": NEW, "code": last_code(NEW)})).status_code == 200


async def test_a_code_works_once_and_a_new_one_cancels_the_old(client, workspace):
    await signup(client)
    await client.post("/v1/auth/login/start", json={"email": NEW})
    first = last_code(NEW)
    await client.post("/v1/auth/login/start", json={"email": NEW})
    second = last_code(NEW)
    assert first != second
    assert (await client.post("/v1/auth/login/verify", json={"email": NEW, "code": first})).status_code == 401
    assert (await client.post("/v1/auth/login/verify", json={"email": NEW, "code": second})).status_code == 200
    assert (
        await client.post("/v1/auth/login/verify", json={"email": NEW, "code": second})
    ).status_code == 401  # single use


async def test_expired_code_is_refused(client, workspace, maker):
    await signup(client)
    await client.post("/v1/auth/login/start", json={"email": NEW})
    async with maker() as db:
        row = (await db.execute(select(AuthCode).where(AuthCode.purpose == "login"))).scalar_one()
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (await client.post("/v1/auth/login/verify", json={"email": NEW, "code": last_code(NEW)})).status_code == 401


async def test_a_signup_code_cannot_be_used_to_log_in(client, workspace):
    code = await invite_for(client)
    await client.post("/v1/auth/signup/start", json={"invite_code": code})
    r = await client.post("/v1/auth/login/verify", json={"email": NEW, "code": last_code(NEW)})
    assert r.status_code == 401


# ---------- no account enumeration ----------
async def test_login_start_looks_identical_for_unknown_and_known_emails(client, workspace):
    await signup(client)
    registry.get_email().sent.clear()
    known = await client.post("/v1/auth/login/start", json={"email": NEW})
    unknown = await client.post("/v1/auth/login/start", json={"email": "nobody@startup.example.com"})
    assert known.status_code == unknown.status_code == 200 and known.json() == unknown.json()
    assert [m["to"] for m in registry.get_email().sent] == [NEW]  # only the real account gets an email
    bad_unknown = await client.post(
        "/v1/auth/login/verify", json={"email": "nobody@startup.example.com", "code": "123456"}
    )
    bad_known = await client.post("/v1/auth/login/verify", json={"email": NEW, "code": "123456"})
    assert bad_unknown.status_code == bad_known.status_code == 401 and bad_unknown.json() == bad_known.json()


async def test_input_validation(client, workspace):
    assert (await client.post("/v1/auth/login/start", json={"email": "not-an-email"})).status_code == 422
    for code in ("12345", "1234567", "abcdef", ""):
        assert (await client.post("/v1/auth/login/verify", json={"email": NEW, "code": code})).status_code == 422


# ---------- rate limits ----------
async def test_login_start_is_limited_per_email(client, workspace):
    await signup(client)
    codes = [await client.post("/v1/auth/login/start", json={"email": NEW}) for _ in range(6)]
    assert [r.status_code for r in codes] == [200, 200, 200, 200, 200, 429]


async def test_verify_attempts_are_throttled(client, workspace):
    statuses = [
        (await client.post("/v1/auth/login/verify", json={"email": NEW, "code": "123456"})).status_code
        for _ in range(12)
    ]
    assert statuses[:10] == [401] * 10 and statuses[10:] == [429, 429]


# ---------- sessions ----------
async def test_only_a_hash_of_the_token_is_stored_and_logout_revokes_it(client, workspace, maker):
    s = await signup(client)
    async with maker() as db:
        row = (await db.execute(select(UserSession))).scalar_one()
        assert s["token"] not in row.token_hash and len(row.token_hash) == 64
    assert (await client.post("/v1/auth/logout", headers=bearer(s["token"]))).status_code == 200
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 401


async def test_sessions_list_revoke_and_logout_everywhere(client, workspace):
    a = await signup(client)
    b = await login(client)
    c = await login(client)
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


async def test_absolute_and_idle_expiry(client, workspace, maker):
    s = await signup(client)
    async with maker() as db:
        row = (await db.execute(select(UserSession))).scalar_one()
        row.last_used_at = datetime.now(UTC) - timedelta(days=8)  # idle 7 days is the limit
        await db.commit()
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 401
    s2 = await login(client)
    async with maker() as db:
        row = (await db.execute(select(UserSession).where(UserSession.revoked_at.is_(None)))).scalars().all()[-1]
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (await client.get("/v1/me", headers=bearer(s2["token"]))).status_code == 401


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


# ---------- two-factor ----------
async def enrol(client, token):
    h = bearer(token)
    setup = (await client.post("/v1/auth/mfa/setup", headers=h)).json()
    r = await client.post("/v1/auth/mfa/enable", json={"code": now_code(setup["secret"])}, headers=h)
    assert r.status_code == 200, r.text
    return setup["secret"], r.json()["recovery_codes"]


async def test_enrolment_needs_a_correct_code_and_returns_recovery_codes(client, workspace, maker):
    s = await signup(client)
    h = bearer(s["token"])
    setup = (await client.post("/v1/auth/mfa/setup", headers=h)).json()
    assert setup["otpauth_uri"].startswith("otpauth://") and setup["secret"] in setup["otpauth_uri"]
    assert (await client.post("/v1/auth/mfa/enable", json={"code": "000000"}, headers=h)).status_code == 422
    r = await client.post("/v1/auth/mfa/enable", json={"code": now_code(setup["secret"])}, headers=h)
    codes = r.json()["recovery_codes"]
    assert len(codes) == 8 and all(re.fullmatch(r"[0-9a-f]{5}-[0-9a-f]{5}", c) for c in codes)
    async with maker() as db:
        u = (await db.execute(select(User).where(User.email == NEW))).scalar_one()
        assert u.totp_enabled and setup["secret"] not in u.totp_secret_enc  # encrypted at rest
        assert len((await db.execute(select(RecoveryCode))).scalars().all()) == 8
        assert codes[0].replace("-", "") not in str((await db.execute(select(RecoveryCode.code_hash))).scalars().all())
    assert (await client.post("/v1/auth/mfa/setup", headers=h)).status_code == 409  # already on


async def test_after_enrolment_login_needs_the_second_factor(client, workspace):
    s = await signup(client)
    secret, _ = await enrol(client, s["token"])
    assert (
        await client.get("/v1/me", headers=bearer(s["token"]))
    ).status_code == 200  # the enrolling session stays valid
    again = await login(client)
    assert again["mfa_required"] is True
    h = bearer(again["token"])
    blocked = await client.get("/v1/me", headers=h)
    assert blocked.status_code == 401 and blocked.json()["detail"]["error"] == "mfa_required"
    assert (await client.get("/v1/auth/status", headers=h)).json() == {
        "email": NEW,
        "mfa_enabled": True,
        "mfa_verified": False,
        "is_operator": False,
        "mfa_enrolment_required": False,
    }
    assert (await client.post("/v1/auth/mfa/verify", json={"code": "000000"}, headers=h)).status_code == 401
    ok = await client.post(
        "/v1/auth/mfa/verify", json={"code": now_code(secret, 1)}, headers=h
    )  # next step is within the window
    assert ok.status_code == 200 and (await client.get("/v1/me", headers=h)).status_code == 200


async def test_a_used_authenticator_code_cannot_be_replayed(client, workspace):
    s = await signup(client)
    secret, _ = await enrol(client, s["token"])
    code = now_code(secret, 1)
    one = await login(client)
    assert (
        await client.post("/v1/auth/mfa/verify", json={"code": code}, headers=bearer(one["token"]))
    ).status_code == 200
    two = await login(client)
    assert (
        await client.post("/v1/auth/mfa/verify", json={"code": code}, headers=bearer(two["token"]))
    ).status_code == 401


async def test_recovery_codes_work_once(client, workspace):
    s = await signup(client)
    _, codes = await enrol(client, s["token"])
    one = await login(client)
    r = await client.post("/v1/auth/mfa/verify", json={"code": codes[0].upper()}, headers=bearer(one["token"]))
    assert r.status_code == 200 and r.json()["recovery_code_used"] is True
    two = await login(client)
    assert (
        await client.post("/v1/auth/mfa/verify", json={"code": codes[0]}, headers=bearer(two["token"]))
    ).status_code == 401
    assert (
        await client.post("/v1/auth/mfa/verify", json={"code": codes[1]}, headers=bearer(two["token"]))
    ).status_code == 200


async def test_enabling_mfa_signs_out_other_devices(client, workspace):
    a = await signup(client)
    b = await login(client)
    await enrol(client, a["token"])
    assert (await client.get("/v1/me", headers=bearer(b["token"]))).status_code == 401
    assert (await client.get("/v1/me", headers=bearer(a["token"]))).status_code == 200


async def test_a_regular_user_can_turn_mfa_off_with_a_code(client, workspace):
    s = await signup(client)
    secret, _ = await enrol(client, s["token"])
    h = bearer(s["token"])
    assert (await client.post("/v1/auth/mfa/disable", json={"code": "000000"}, headers=h)).status_code == 401
    assert (await client.post("/v1/auth/mfa/disable", json={"code": now_code(secret, 1)}, headers=h)).status_code == 200
    assert (await login(client))["mfa_required"] is False


async def test_new_recovery_codes_replace_the_old_ones(client, workspace):
    s = await signup(client)
    secret, old = await enrol(client, s["token"])
    h = bearer(s["token"])
    new = (await client.post("/v1/auth/mfa/recovery-codes", json={"code": now_code(secret, 1)}, headers=h)).json()[
        "recovery_codes"
    ]
    assert len(new) == 8 and set(new).isdisjoint(old)
    one = await login(client)
    assert (
        await client.post("/v1/auth/mfa/verify", json={"code": old[0]}, headers=bearer(one["token"]))
    ).status_code == 401


async def test_mfa_verify_is_throttled(client, workspace):
    s = await signup(client)
    await enrol(client, s["token"])
    h = bearer((await login(client))["token"])
    statuses = [
        (await client.post("/v1/auth/mfa/verify", json={"code": "000000"}, headers=h)).status_code for _ in range(12)
    ]
    assert statuses[:8] == [401] * 8 and 429 in statuses  # shares the per-IP budget with the sign-in calls above


# ---------- operators ----------
async def operator_session(client, maker):
    r = await client.post("/v1/auth/login/start", json={"email": "ops@example.com"})
    assert r.status_code == 200
    return (
        await client.post(
            "/v1/auth/login/verify", json={"email": "ops@example.com", "code": last_code("ops@example.com")}
        )
    ).json()


async def test_operators_must_enrol_before_the_console_opens(client, workspace, maker):
    s = await operator_session(client, maker)
    assert s["mfa_enrolment_required"] is True and s["mfa_required"] is False
    h = bearer(s["token"])
    assert (await client.get("/v1/me", headers=h)).status_code == 200  # an operator is still a normal user
    blocked = await client.get("/v1/admin/queue", headers=h)
    assert blocked.status_code == 403 and blocked.json()["detail"]["error"] == "mfa_enrolment_required"
    secret, _ = await enrol(client, s["token"])
    assert (await client.get("/v1/admin/queue", headers=h)).status_code == 200
    again = await operator_session(client, maker)
    assert again["mfa_required"] is True and again["mfa_enrolment_required"] is False
    ha = bearer(again["token"])
    assert (await client.get("/v1/admin/queue", headers=ha)).status_code == 401  # password-less alone isn't enough
    await client.post("/v1/auth/mfa/verify", json={"code": now_code(secret, 1)}, headers=ha)
    assert (await client.get("/v1/admin/queue", headers=ha)).status_code == 200


async def test_operators_cannot_turn_mfa_off_and_have_short_sessions(client, workspace, maker):
    s = await operator_session(client, maker)
    secret, _ = await enrol(client, s["token"])
    r = await client.post("/v1/auth/mfa/disable", json={"code": now_code(secret, 1)}, headers=bearer(s["token"]))
    assert r.status_code == 403
    async with maker() as db:
        row = (await db.execute(select(UserSession).order_by(UserSession.created_at.desc()))).scalars().first()
        assert (
            timedelta(hours=7, minutes=59)
            < row.expires_at.replace(tzinfo=UTC) - row.created_at.replace(tzinfo=UTC)
            < timedelta(hours=8, minutes=1)
        )
        row.last_used_at = datetime.now(UTC) - timedelta(hours=2)  # operators idle out after an hour
        await db.commit()
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 401


async def test_operator_sign_ins_and_mfa_changes_are_audited(client, workspace, maker):
    s = await operator_session(client, maker)
    await enrol(client, s["token"])
    async with maker() as db:
        actions = [a.action for a in (await db.execute(select(AuditLog).order_by(AuditLog.created_at))).scalars()]
    assert "auth.login" in actions and "auth.mfa_enabled" in actions


async def test_cli_reset_clears_two_factor_and_signs_the_user_out(client, workspace, maker):
    s = await signup(client)
    await enrol(client, s["token"])
    assert await reset_mfa(NEW.upper()) is True
    assert (await client.get("/v1/me", headers=bearer(s["token"]))).status_code == 401
    assert (await login(client))["mfa_required"] is False
    async with maker() as db:
        assert (
            await db.execute(select(AuditLog).where(AuditLog.action == "auth.mfa_reset"))
        ).scalar_one().actor == "cli"
    assert await reset_mfa("ghost@x.example.com") is False


async def test_dev_mailbox_endpoint_exists_only_for_local_mock_mail(client, workspace):
    await client.post("/v1/admin/invites", json={"email": NEW, "workspace_name": "X"}, headers=OPS)
    registry.get_email().sent.append({"to": NEW, "subject": "s", "text": "code 123456"})
    r = await client.get("/v1/dev/last-email", params={"to": NEW})
    assert r.status_code == 200 and "123456" in r.json()["text"]
    assert (await client.get("/v1/dev/last-email", params={"to": "none@x.example.com"})).status_code == 404
