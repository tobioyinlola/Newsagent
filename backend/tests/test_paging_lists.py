"""The lists customers and the team scroll through are paged: a page of rows, the total, and a hard ceiling on the page size."""

from datetime import timedelta
from decimal import Decimal

from app.models import AuditLog, CreditTransaction, DistributionRequest, Project
from app.models.base import utcnow
from tests.conftest import OPS, OWNER


async def _fill(maker, rows):
    async with maker() as db:
        db.add_all(rows)
        await db.commit()


def _ids(rows):
    return [r["id"] for r in rows]


async def test_audit_log_pages_in_a_stable_order_and_reports_the_total(client, workspace, maker):
    now = utcnow()
    await _fill(maker, [AuditLog(actor="a@b.c", action="test.paging", created_at=now - timedelta(minutes=i)) for i in range(30)])
    first = await client.get("/v1/admin/audit?action=test.paging&limit=10", headers=OPS)
    assert first.status_code == 200 and len(first.json()) == 10 and first.headers["x-total-count"] == "30"
    second = await client.get("/v1/admin/audit?action=test.paging&limit=10&offset=10", headers=OPS)
    last = await client.get("/v1/admin/audit?action=test.paging&limit=10&offset=20", headers=OPS)
    seen = _ids(first.json()) + _ids(second.json()) + _ids(last.json())
    assert len(seen) == 30 and len(set(seen)) == 30  # every row exactly once across the pages
    assert (await client.get("/v1/admin/audit?action=test.paging&limit=10&offset=30", headers=OPS)).json() == []


async def test_nobody_can_ask_for_an_unbounded_page(client, workspace):
    for path in ("/v1/admin/audit?limit=100000", "/v1/admin/jobs?limit=0", "/v1/projects?limit=201", "/v1/billing/ledger?offset=-1"):
        assert (await client.get(path, headers=OPS if "/admin/" in path else OWNER)).status_code == 422, path


async def test_a_customers_videos_page_and_can_be_narrowed_by_stage(client, workspace, maker):
    now = utcnow()
    await _fill(
        maker,
        [Project(workspace_id=workspace, state="final_ready" if i % 3 == 0 else "draft", created_at=now - timedelta(minutes=i)) for i in range(25)],
    )
    page = await client.get("/v1/projects?limit=10&offset=20", headers=OWNER)
    assert len(page.json()) == 5 and page.headers["x-total-count"] == "25"
    done = await client.get("/v1/projects?state=final_ready&limit=1", headers=OWNER)
    assert done.headers["x-total-count"] == "9" and len(done.json()) == 1  # the dashboard counts finished videos without loading them all


async def test_the_ledger_pages(client, workspace, maker):
    now = utcnow()
    await _fill(
        maker,
        [
            CreditTransaction(workspace_id=workspace, kind="grant", amount=Decimal(1), balance_after=Decimal(i + 1), ref=f"paging-{i}", created_at=now - timedelta(minutes=i))
            for i in range(12)
        ],
    )
    r = await client.get("/v1/billing/ledger?limit=5&offset=5", headers=OWNER)
    assert len(r.json()) == 5 and int(r.headers["x-total-count"]) >= 12


async def test_distribution_requests_page_for_the_customer_and_the_team(client, workspace, maker):
    now = utcnow()
    await _fill(maker, [DistributionRequest(workspace_id=workspace, created_by="owner@acme.test", data={}, updated_at=now - timedelta(minutes=i)) for i in range(7)])
    mine = await client.get("/v1/distribution?limit=3&offset=3", headers=OWNER)
    assert mine.status_code == 200 and len(mine.json()) == 3 and mine.headers["x-total-count"] == "7"
    team = await client.get("/v1/admin/distribution?limit=2", headers=OPS)
    assert len(team.json()) == 2 and int(team.headers["x-total-count"]) >= 7
    drafts = await client.get("/v1/admin/distribution?paid=false&limit=100", headers=OPS)
    assert all(not r["paid"] for r in drafts.json()) and int(drafts.headers["x-total-count"]) >= 7  # the filter is applied before paging
    assert int((await client.get("/v1/admin/distribution?paid=true", headers=OPS)).headers["x-total-count"]) == 0


async def test_marketing_lists_carry_their_total(client, workspace):
    for i in range(3):
        r = await client.post("/v1/admin/marketing/segments", json={"name": f"Seg {i}", "description": "", "rules": {"match": "all", "conditions": [{"field": "country", "op": "in", "value": ["Nigeria"]}]}}, headers=OPS)
        assert r.status_code == 201, r.text
    r = (await client.get("/v1/admin/marketing/segments?limit=2&offset=1", headers=OPS)).json()
    assert len(r["items"]) == 2 and r["total"] == 3 and r["limit"] == 2 and r["offset"] == 1


async def test_outreach_threads_report_a_total(client, workspace):
    r = (await client.get("/v1/admin/outreach/threads?limit=10", headers=OPS)).json()
    assert {"threads", "counts", "total", "limit", "offset"} <= set(r)


async def test_the_revenue_page_pages_payments_and_companies(client, workspace):
    r = (await client.get("/v1/admin/payments?limit=5&companies_limit=3", headers=OPS)).json()
    assert {"items_total", "companies_total", "limit", "offset"} <= set(r)
    assert len(r["items"]) <= 5 and len(r["paying_companies"]) <= 3


async def test_places_in_line_stay_right_on_the_second_page(client, workspace, maker):
    from app.models import WorkItem

    now = utcnow()
    async with maker() as db:
        for i in range(6):
            db.add(
                WorkItem(
                    project_id=f"line-project-{i}",
                    workspace_id=workspace,
                    lane="render",
                    step="final_render",
                    state="waiting",
                    priority=0,
                    enqueued_at=now + timedelta(seconds=i),
                )
            )
        await db.commit()
    whole = (await client.get("/v1/admin/line?limit=100", headers=OPS)).json()
    second = (await client.get("/v1/admin/line?limit=3&offset=3", headers=OPS)).json()
    assert [i["position"] for i in whole] == [1, 2, 3, 4, 5, 6]
    assert [i["position"] for i in second] == [4, 5, 6]  # still 4 to 6, not 1 to 3 again


async def test_workspaces_can_be_found_by_name_and_page(client, workspace):
    for name in ("Findable Alpha Ltd", "Findable Beta Ltd", "Someone Else"):
        assert (await client.post("/v1/admin/invites", json={"email": f"{name[:6].lower()}{len(name)}@example.com", "workspace_name": name, "credits": "1"}, headers=OPS)).status_code == 200
    found = await client.get("/v1/admin/workspaces?q=findable&limit=1", headers=OPS)
    assert len(found.json()) == 1 and found.headers["x-total-count"] == "2"
    second = await client.get("/v1/admin/workspaces?q=findable&limit=1&offset=1", headers=OPS)
    assert second.json()[0]["id"] != found.json()[0]["id"]


async def test_a_customers_payments_and_videos_page_separately_with_the_true_total_paid(client, workspace, maker):
    await _fill(maker, [Project(workspace_id=workspace, state="draft", created_at=utcnow() - timedelta(minutes=i)) for i in range(12)])
    r = (await client.get(f"/v1/admin/customers/{workspace}?limit=5&offset=10", headers=OPS)).json()
    assert r["projects_total"] == 12 and len(r["projects"]) == 2
    assert {"payments_total", "paid_usd"} <= set(r)
