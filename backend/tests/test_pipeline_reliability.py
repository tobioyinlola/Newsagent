"""Crash safety, retries, cancellation and recovery for paid vendor work. Vendors are mocks (no real HeyGen call)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app import jobs
from app.integrations import registry
from app.integrations.avatar.base import AvatarPoll
from app.integrations.avatar.mock import MockAvatarProvider
from app.integrations.errors import ProviderError, classify
from app.models import Job, Project, ProviderRequest
from app.pipeline.queue import InlineQueue, Queue, get_queue, set_queue
from app.services import provider_requests
from tests.conftest import OWNER
from tests.helpers import BRIEF


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(provider_requests, "POLL_INTERVAL_S", 0.0)


class AsyncVendor(MockAvatarProvider):
    """Behaves like a vendor with separate submit and poll steps (as HeyGen does), and counts every paid submission."""

    supports_async = True

    def __init__(self):
        super().__init__()
        self.submits = 0
        self.polls = 0
        self.crash_on_poll: int | None = None  # raise on this poll number, like a worker dying mid-wait
        self.pending_polls = 1
        self.submit_error: Exception | None = None
        self.on_poll = None

    async def submit(self, req):
        if self.submit_error:
            raise self.submit_error
        self.submits += 1
        return f"vid-{self.submits}"

    async def poll(self, vendor_id, req):
        self.polls += 1
        if self.on_poll:
            await self.on_poll()
        if self.crash_on_poll == self.polls:
            raise RuntimeError("worker died")
        if self.polls <= self.pending_polls:
            return AvatarPoll("pending")
        return AvatarPoll("completed", await super().generate(req))


async def approved_project(client, drain=True):
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme, a farm marketplace."}]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    if drain:
        await get_queue().drain()
    return pid


async def assert_billed_once(maker, pid, workspace):
    """One credit hold for the clip however many attempts it took, and the ledger still adds up."""
    from app.models import CreditTransaction, Workspace
    from app.services.ledger import ledger_sum

    async with maker() as s:
        usage = (
            (
                await s.execute(
                    select(CreditTransaction).where(
                        CreditTransaction.project_id == pid,
                        CreditTransaction.stage == "anchor",
                        CreditTransaction.kind == "usage",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(usage) == 1, [(t.kind, t.amount) for t in usage]
        assert await ledger_sum(s, workspace) == (await s.get(Workspace, workspace)).credit_balance


async def state(client, pid):
    return (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()


# ---------- error classification ----------
def http_error(code, headers=None):
    req = httpx.Request("POST", "https://x.test")
    return httpx.HTTPStatusError("boom", request=req, response=httpx.Response(code, headers=headers or {}, request=req))


@pytest.mark.parametrize(
    ("exc", "category", "retryable"),
    [
        (http_error(401), "auth", False),
        (http_error(403), "auth", False),
        (http_error(422), "invalid_input", False),
        (http_error(404), "invalid_input", False),
        (http_error(429, {"retry-after": "7"}), "rate_limited", True),
        (http_error(503), "temporary", True),
        (httpx.ConnectError("no route"), "temporary", True),
        (httpx.ReadTimeout("slow"), "timeout", True),
        (TimeoutError(), "timeout", True),
        (ProviderError("x", "invalid_input"), "invalid_input", False),
        (RuntimeError("???"), "unknown", True),
    ],
)
def test_errors_are_classified(exc, category, retryable):
    c = classify(exc)
    assert (c.category, c.retryable) == (category, retryable)


def test_rate_limit_hint_is_kept_and_capped():
    assert classify(http_error(429, {"retry-after": "7"})).retry_after == 7
    assert classify(http_error(429, {"retry-after": "9999"})).retry_after == 120
    assert classify(http_error(429)).retry_after is None


# ---------- never pay twice ----------
async def test_a_crash_while_waiting_resumes_the_same_vendor_job(client, workspace, maker):
    vendor = AsyncVendor()
    vendor.crash_on_poll = 1  # first attempt dies after the vendor accepted the job
    registry.override(avatar=vendor)
    pid = await approved_project(client)
    assert (await state(client, pid))["state"] == "final_ready"
    assert vendor.submits == 1, "the retry must poll the recorded vendor id, not submit a second paid video"
    async with maker() as s:
        rows = (await s.execute(select(ProviderRequest).where(ProviderRequest.project_id == pid))).scalars().all()
    assert len(rows) == 1 and rows[0].status == "completed" and rows[0].vendor_video_id == "vid-1"
    assert rows[0].result["duration_s"] > 0 and rows[0].attempts == 1 and rows[0].hold is None  # settled
    await assert_billed_once(maker, pid, workspace)


async def test_the_same_request_twice_is_one_paid_generation(client, workspace, maker):
    vendor = AsyncVendor()
    vendor.pending_polls = 0
    registry.override(avatar=vendor)
    pid = await approved_project(client)
    from app.config import VENDOR_POLICIES
    from app.integrations.avatar.base import AvatarRequest

    req = AvatarRequest(script_text="same words", voice_accent="british")
    kw = {
        "project_id": pid,
        "slot": "slot-a",
        "request_hash": "h1",
        "policy": VENDOR_POLICIES["avatar"],
        "is_cancelled": lambda: _false(),
    }
    before = vendor.submits
    a = await provider_requests.generate(vendor, req, **kw)
    b = await provider_requests.generate(vendor, req, **kw)
    assert vendor.submits == before + 1
    assert a.vendor_video_id == b.vendor_video_id or a.duration_s == b.duration_s
    c = await provider_requests.generate(vendor, req, **{**kw, "request_hash": "h2"})  # different inputs: a new job
    assert vendor.submits == before + 2 and c


async def _false():
    return False


async def test_vendor_concurrency_is_capped(client, workspace, maker):
    vendor = AsyncVendor()
    registry.override(avatar=vendor)
    pid = await approved_project(client)
    from app.config import VendorPolicy
    from app.integrations.avatar.base import AvatarRequest

    async with maker() as s:  # three jobs are already in flight at this vendor
        for i in range(3):
            s.add(ProviderRequest(project_id=pid, provider="mock", slot=f"s{i}", request_hash="x", status="submitted"))
        await s.commit()
    with pytest.raises(ProviderError) as e:
        await provider_requests.generate(
            vendor,
            AvatarRequest(script_text="more", voice_accent="british"),
            project_id=pid,
            slot="new",
            request_hash="n",
            policy=VendorPolicy(max_concurrency=3),
            is_cancelled=_false,
        )
    assert e.value.category == "busy" and e.value.retryable


# ---------- retry decisions ----------
async def test_bad_credentials_are_not_retried_and_operators_are_told(client, workspace, maker):
    vendor = AsyncVendor()
    vendor.submit_error = http_error(401)
    registry.override(avatar=vendor)
    registry.get_email().sent.clear()
    pid = await approved_project(client)
    p = await state(client, pid)
    assert p["state"] == "failed" and "temporarily unavailable" in p["failure_reason"]
    async with maker() as s:
        job = (await s.execute(select(Job).where(Job.project_id == pid, Job.stage == "anchor_render"))).scalar_one()
    assert job.attempts == 1 and job.failure_category == "auth" and job.error.startswith("[auth]")
    assert any(m["subject"] == "Provider rejected our credentials" for m in registry.get_email().sent)


async def test_a_refused_request_is_not_retried(client, workspace, maker):
    vendor = AsyncVendor()
    vendor.submit_error = http_error(422)
    registry.override(avatar=vendor)
    pid = await approved_project(client)
    assert (await state(client, pid))["state"] == "failed"
    async with maker() as s:
        job = (await s.execute(select(Job).where(Job.project_id == pid, Job.stage == "anchor_render"))).scalar_one()
    assert job.attempts == 1 and job.failure_category == "invalid_input"


async def test_a_rate_limit_is_retried_then_succeeds(client, workspace, maker):
    vendor = AsyncVendor()
    vendor.submit_error = http_error(429, {"retry-after": "1"})
    vendor.pending_polls = 0
    registry.override(avatar=vendor)

    original = vendor.submit

    async def heals(req):
        if vendor.submit_error and getattr(heals, "n", 0) >= 1:
            vendor.submit_error = None
        heals.n = getattr(heals, "n", 0) + 1
        return await original(req)

    vendor.submit = heals
    pid = await approved_project(client)
    assert (await state(client, pid))["state"] == "final_ready"
    async with maker() as s:
        job = (await s.execute(select(Job).where(Job.project_id == pid, Job.stage == "anchor_render"))).scalar_one()
    assert job.attempts == 2


# ---------- cancel and resume ----------
async def test_cancelling_stops_the_work_and_resuming_reuses_the_vendor_job(client, workspace, maker):
    vendor = AsyncVendor()
    vendor.pending_polls = 1
    registry.override(avatar=vendor)

    async def cancel_during_wait():
        if vendor.polls == 1:
            assert (await client.post(f"/v1/projects/{pid_box[0]}/cancel", headers=OWNER)).status_code == 200

    vendor.on_poll = cancel_during_wait
    pid_box: list[str] = []
    r = await client.post("/v1/projects", json=BRIEF, headers=OWNER)
    pid_box.append(r.json()["id"])
    pid = pid_box[0]
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme."}]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    await get_queue().drain()
    p = await state(client, pid)
    assert p["state"] == "cancelled" and "cancelled" in p["failure_reason"]
    assert vendor.submits == 1
    vendor.on_poll = None
    assert (await client.post(f"/v1/projects/{pid}/retry", headers=OWNER)).status_code == 200
    await get_queue().drain()
    assert (await state(client, pid))["state"] == "final_ready"
    assert vendor.submits == 1, "the cancelled vendor job was resumed, not paid for again"
    await assert_billed_once(maker, pid, workspace)


async def test_only_a_video_in_progress_can_be_cancelled(client, workspace):
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    assert (await client.post(f"/v1/projects/{pid}/cancel", headers=OWNER)).status_code == 409  # still a draft
    done = await approved_project(client)
    assert (await state(client, done))["state"] == "final_ready"
    assert (await client.post(f"/v1/projects/{done}/cancel", headers=OWNER)).status_code == 409


async def test_nobody_else_can_cancel_my_video(client, workspace, maker):
    pid = await approved_project(client, drain=False)
    other = {"Authorization": "Bearer dev:someone@else.test"}
    assert (await client.post(f"/v1/projects/{pid}/cancel", headers=other)).status_code in {401, 403, 404}
    await get_queue().drain()


# ---------- recovery after a restart ----------
class Lost(Queue):
    """A queue that loses every message, like a restart with an in-memory queue or a dropped broker message."""

    def enqueue(self, step, payload, delay=0.0):
        return None


async def test_a_project_left_behind_by_a_restart_is_re_driven(client, workspace, maker):
    set_queue(Lost())
    pid = await approved_project(client, drain=False)
    assert (await state(client, pid))["state"] == "rendering_anchor"
    set_queue(InlineQueue())
    assert await jobs.reconcile_projects() == 0  # it only just started: leave it alone
    async with maker() as s:
        p = await s.get(Project, pid)
        p.state_changed_at = datetime.now(UTC) - timedelta(hours=1)
        await s.commit()
    assert await jobs.reconcile_projects() == 1
    await get_queue().drain()
    assert (await state(client, pid))["state"] == "final_ready"
    assert await jobs.reconcile_projects() == 0


async def test_a_fresh_running_job_is_left_alone(client, workspace, maker):
    set_queue(Lost())
    pid = await approved_project(client, drain=False)
    async with maker() as s:
        p = await s.get(Project, pid)
        p.state_changed_at = datetime.now(UTC) - timedelta(hours=1)
        s.add(
            Job(project_id=pid, stage="anchor_render", input_hash="x", status="running", started_at=datetime.now(UTC))
        )
        await s.commit()
    assert await jobs.reconcile_projects() == 0


# ---------- progress ----------
async def test_progress_reports_each_piece_and_who_may_see_it(client, workspace):
    pid = await approved_project(client)
    r = (await client.get(f"/v1/projects/{pid}/progress", headers=OWNER)).json()
    assert r["state"] == "final_ready" and r["percent"] == 100 and not r["cancellable"]
    assert [s["status"] for s in r["stages"]] == ["done"] * len(r["stages"])
    other = {"Authorization": "Bearer dev:someone@else.test"}
    assert (await client.get(f"/v1/projects/{pid}/progress", headers=other)).status_code in {401, 403, 404}


async def test_progress_points_at_the_piece_that_failed(client, workspace):
    vendor = AsyncVendor()
    vendor.submit_error = http_error(422)
    registry.override(avatar=vendor)
    pid = await approved_project(client)
    r = (await client.get(f"/v1/projects/{pid}/progress", headers=OWNER)).json()
    by = {s["key"]: s for s in r["stages"]}
    assert by["script"]["status"] == "done" and by["presenter"]["status"] == "failed"
    assert by["render"]["status"] == "pending" and r["failure_category"] == "invalid_input" and r["retryable"]
    assert r["percent"] < 50


async def test_progress_shows_a_cancelled_project(client, workspace):
    vendor = AsyncVendor()
    vendor.pending_polls = 10**6  # never finishes on its own
    registry.override(avatar=vendor)

    async def cancel_now():
        await client.post(f"/v1/projects/{pid_box[0]}/cancel", headers=OWNER)

    vendor.on_poll = cancel_now
    pid_box: list[str] = []
    r = await client.post("/v1/projects", json=BRIEF, headers=OWNER)
    pid = r.json()["id"]
    pid_box.append(pid)
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    await get_queue().drain()
    r = (await client.get(f"/v1/projects/{pid}/progress", headers=OWNER)).json()
    assert r["state"] == "cancelled" and r["retryable"] and not r["cancellable"]
    assert any(s["status"] == "cancelled" for s in r["stages"])
