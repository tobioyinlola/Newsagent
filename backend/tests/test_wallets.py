"""Back office: every wallet's balance, what was bought and used, and each wallet's history."""

from decimal import Decimal

from app.models import User, Workspace
from app.services import ledger
from tests.conftest import OPS, OWNER


async def _second_wallet(maker):
    async with maker() as s:
        ws = Workspace(name="Beta Foods", credit_balance=Decimal("0"))
        s.add(ws)
        await s.flush()
        s.add(User(email="beta@foods.example.com", workspace_id=ws.id))
        await ledger.apply(s, ws, Decimal("1"), "grant", description="Welcome credit", ref="g1")
        await ledger.apply(s, ws, Decimal("20"), "purchase", description="Card payment", ref="p1")
        await ledger.apply(
            s,
            ws,
            Decimal("-1"),
            "usage",
            project_id="proj1",
            stage="video",
            description="Video (1 credit)",
            ref="video:proj1",
        )
        await ledger.apply(
            s,
            ws,
            Decimal("-18.8"),
            "usage",
            stage="distribution",
            description="Distribution to 1 outlets",
            ref="distribution:d1",
        )
        await ledger.apply(
            s, ws, Decimal("0.5"), "adjustment", description='=HYPERLINK("x")', ref="a1"
        )  # a cell that looks like a formula
        await s.commit()
        return ws.id


async def test_every_wallet_is_listed_with_what_was_bought_free_and_used(client, workspace, maker):
    beta = await _second_wallet(maker)
    r = (await client.get("/v1/admin/wallets", headers=OPS)).json()
    rows = {x["company"]: x for x in r["items"]}
    b = rows["Beta Foods"]
    assert (b["workspace_id"], b["owner_email"]) == (beta, "beta@foods.example.com")
    assert Decimal(b["balance"]) == Decimal("1.7")  # 1 free + 20 bought - 1 - 18.8 + 0.5 adjusted
    assert (Decimal(b["bought"]), Decimal(b["free"]), Decimal(b["used"])) == (
        Decimal("20"),
        Decimal("1"),
        Decimal("19.8"),
    )
    assert b["last_activity_at"] is not None and b["status"] == "active"
    acme = rows["Acme"]
    assert (
        Decimal(acme["balance"]) == Decimal("10")
        and Decimal(acme["free"]) == Decimal("10")
        and Decimal(acme["used"]) == 0
    )
    assert r["totals"]["wallets"] == 2 and r["total"] == 2
    assert Decimal(r["totals"]["balance"]) == Decimal(acme["balance"]) + Decimal(b["balance"])
    assert Decimal(r["totals"]["used"]) == Decimal("19.8") and Decimal(r["totals"]["bought"]) == 20


async def test_wallets_can_be_searched_and_sorted(client, workspace, maker):
    await _second_wallet(maker)
    low = (await client.get("/v1/admin/wallets", params={"sort": "balance_low"}, headers=OPS)).json()["items"]
    high = (await client.get("/v1/admin/wallets", params={"sort": "balance_high"}, headers=OPS)).json()["items"]
    assert [x["company"] for x in low] == [x["company"] for x in reversed(high)]
    assert [
        x["company"]
        for x in (await client.get("/v1/admin/wallets", params={"sort": "used_high"}, headers=OPS)).json()["items"]
    ][0] == "Beta Foods"
    assert [
        x["company"] for x in (await client.get("/v1/admin/wallets", params={"q": "beta"}, headers=OPS)).json()["items"]
    ] == ["Beta Foods"]
    assert [
        x["company"]
        for x in (await client.get("/v1/admin/wallets", params={"q": "owner@acme"}, headers=OPS)).json()["items"]
    ] == ["Acme"]
    assert (await client.get("/v1/admin/wallets", params={"sort": "nonsense"}, headers=OPS)).status_code == 422
    paged = (await client.get("/v1/admin/wallets", params={"limit": 1, "offset": 1}, headers=OPS)).json()
    assert paged["total"] == 2 and len(paged["items"]) == 1


async def test_a_wallets_history_shows_payments_and_usage_separately(client, workspace, maker):
    beta = await _second_wallet(maker)
    allr = (await client.get(f"/v1/admin/customers/{beta}/ledger", headers=OPS)).json()
    assert allr["company"] == "Beta Foods" and allr["total"] == 5
    assert [x["kind"] for x in allr["items"]][:1] == ["adjustment"]  # newest first
    pay = (await client.get(f"/v1/admin/customers/{beta}/ledger", params={"group": "payments"}, headers=OPS)).json()
    assert [x["label"] for x in pay["items"] if x["kind"] != "adjustment"] == ["Credits bought", "Free credits"]
    use = (await client.get(f"/v1/admin/customers/{beta}/ledger", params={"group": "usage"}, headers=OPS)).json()
    assert [(x["description"], Decimal(x["amount"])) for x in use["items"]] == [
        ("Distribution to 1 outlets", Decimal("-18.8")),
        ("Video (1 credit)", Decimal("-1")),
    ]
    assert use["items"][1]["project_id"] == "proj1" and use["items"][1]["stage"] == "video"
    assert Decimal(use["items"][0]["balance_after"]) is not None
    page2 = (
        await client.get(f"/v1/admin/customers/{beta}/ledger", params={"limit": 2, "offset": 2}, headers=OPS)
    ).json()
    assert len(page2["items"]) == 2 and page2["total"] == 5
    assert (await client.get("/v1/admin/customers/nope/ledger", headers=OPS)).status_code == 404


async def test_the_lists_download_as_csv_and_a_cell_never_starts_a_formula(client, workspace, maker):
    beta = await _second_wallet(maker)
    r = await client.get("/v1/admin/wallets.csv", headers=OPS)
    assert (
        r.headers["content-type"].startswith("text/csv")
        and "Beta Foods" in r.text
        and r.text.splitlines()[0].startswith("company,owner_email")
    )
    led = await client.get(f"/v1/admin/customers/{beta}/ledger.csv", params={"group": "all"}, headers=OPS)
    assert "Video (1 credit)" in led.text and "'=HYPERLINK" in led.text and ",=HYPERLINK" not in led.text
    assert (
        await client.get(f"/v1/admin/customers/{beta}/ledger.csv", params={"group": "usage"}, headers=OPS)
    ).text.count("\n") == 3  # a header and two rows


async def test_only_staff_with_customer_access_can_see_wallets(client, workspace):
    for path in (
        "/v1/admin/wallets",
        "/v1/admin/wallets.csv",
        "/v1/admin/customers/x/ledger",
        "/v1/admin/customers/x/ledger.csv",
    ):
        assert (await client.get(path, headers=OWNER)).status_code in {401, 403}
        assert (await client.get(path)).status_code in {401, 403}
