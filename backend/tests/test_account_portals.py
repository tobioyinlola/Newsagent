from sqlalchemy import select

from app.models import StaffMember, User
from app.services import passwords
from tests.conftest import OPS

PW = "A correct test password 123!"


async def test_credentials_are_bound_to_admin_or_customer_entry(client, workspace, maker):
    async with maker() as db:
        customer = (await db.execute(select(User).where(User.email == "owner@acme.test"))).scalar_one()
        customer.email = "customer@example.com"
        users = (await db.execute(select(User))).scalars()
        for user in users:
            user.password_hash = passwords.hash_password(PW)
        await db.commit()
    for email, portal, expected in [
        ("ops@example.com", "customer", 403),
        ("ops@example.com", "admin", 200),
        ("customer@example.com", "admin", 403),
        ("customer@example.com", "customer", 200),
    ]:
        response = await client.post("/v1/auth/login", json={"email": email.upper(), "password": PW, "portal": portal})
        assert response.status_code == expected, response.text
        if expected == 200:
            assert response.json()["otp_required"] == (portal == "admin")
    # The default is the customer portal; changing clients cannot bypass the server rule.
    assert (await client.post("/v1/auth/login", json={"email": "ops@example.com", "password": PW})).status_code == 403
    assert (
        await client.post(
            "/v1/auth/login", json={"email": "ops@example.com", "password": "incorrect", "portal": "customer"}
        )
    ).status_code == 401


async def test_pending_team_addresses_cannot_register_as_customers(client, workspace, maker):
    async with maker() as db:
        db.add(
            StaffMember(
                email="pending@example.com",
                role="viewer",
                permissions=["overview.view"],
                status="invited",
                workspace_id=workspace,
                invited_by="ops@example.com",
            )
        )
        await db.commit()
    response = await client.post(
        "/v1/auth/signup/start",
        json={
            "email": "pending@example.com",
            "business_name": "Test business",
            "city": "Lagos",
            "country": "Nigeria",
            "industry": "technology",
            "password": PW,
        },
    )
    assert response.status_code == 403, response.text
    assert (
        await client.post(
            "/v1/admin/invites", headers=OPS, json={"email": "pending@example.com", "workspace_name": "No duplicate"}
        )
    ).status_code == 409


async def test_team_identity_without_active_permissions_cannot_fall_back_to_customer_login(client, workspace, maker):
    async with maker() as db:
        db.add(
            User(
                email="restricted@example.com",
                role="staff",
                workspace_id=workspace,
                password_hash=passwords.hash_password(PW),
            )
        )
        db.add(
            StaffMember(
                email="restricted@example.com",
                role="custom",
                permissions=[],
                status="active",
                workspace_id=workspace,
                invited_by="ops@example.com",
            )
        )
        await db.commit()
    for portal in ["admin", "customer"]:
        response = await client.post(
            "/v1/auth/login", json={"email": "restricted@example.com", "password": PW, "portal": portal}
        )
        assert response.status_code == 401
