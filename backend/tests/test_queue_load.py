"""Behaviour under load: lanes, de-duplication, a vendor with no free slot, racing workers, a renderer that restarted."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.config import VendorPolicy
from app.integrations import registry
from app.integrations.errors import ProviderError
from app.integrations.renderer.http import HttpRenderer
from app.models import Job, Project, ProviderRequest
from app.pipeline import queue as q
from app.pipeline import runner
from app.pipeline.queue import Queue, set_queue
from app.services import provider_requests
from tests.conftest import OWNER
from tests.helpers import BRIEF
from tests.test_pipeline_reliability import AsyncVendor


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(provider_requests, "POLL_INTERVAL_S", 0.0)


class Recorder(Queue):
    def __init__(self):
        self.calls: list[tuple[str, dict, float]] = []

    def enqueue(self, step, payload, delay=0.0):
        self.calls.append((step, payload, delay))


# ---------- lanes and the queue itself ----------
def test_every_step_has_a_lane_and_quick_work_never_shares_with_slow_work():
    assert q.lane_for("process_take") == q.INTERACTIVE
    assert {q.lane_for(s) for s in ("anchor_render", "question_clips")} == {q.AVATAR}
    assert {q.lane_for(s) for s in ("preview_render", "final_render", "merge_render")} == {q.RENDER}
    assert q.lane_for("something_new") == q.DEFAULT
    assert set(runner.STEPS) <= set(q.STEP_LANE)  # a new pipeline step must be given a lane on purpose


class FakeRedis:
    def __init__(self):
        self.keys: dict[str, str] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    def delete(self, key):
        self.keys.pop(key, None)


def test_celery_queue_routes_by_lane_and_drops_duplicates(monkeypatch):
    from app.pipeline import celery_app as ca

    sent = []
    monkeypatch.setattr(ca.celery_app, "send_task", lambda name, **kw: sent.append(kw))
    fake = FakeRedis()
    monkeypatch.setattr(q, "_redis", lambda: fake)
    cq = q.CeleryQueue()
    cq.enqueue("final_render", {"project_id": "p1"})
    cq.enqueue("final_render", {"project_id": "p1"})  # already waiting: not sent twice
    cq.enqueue("process_take", {"take_id": "t1"}, delay=12)
    assert [(s["queue"], s["args"][0]) for s in sent] == [("render", "final_render"), ("interactive", "process_take")]
    assert sent[1]["countdown"] == 12
    q.release_marker("final_render", {"project_id": "p1"})  # a worker picked it up: it may be queued again
    cq.enqueue("final_render", {"project_id": "p1"})
    assert len(sent) == 3


def test_a_broker_outage_never_breaks_the_request_that_queued_the_work(monkeypatch):
    from app.pipeline import celery_app as ca

    def down(*a, **k):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(ca.celery_app, "send_task", down)
    fake = FakeRedis()
    monkeypatch.setattr(q, "_redis", lambda: fake)
    q.CeleryQueue().enqueue("anchor_render", {"project_id": "p1"})  # does not raise
    assert fake.keys == {}  # the marker is cleared, so the sweep's re-send is not mistaken for a duplicate


def test_without_redis_work_is_still_queued(monkeypatch):
    from app.pipeline import celery_app as ca

    sent = []
    monkeypatch.setattr(ca.celery_app, "send_task", lambda name, **kw: sent.append(kw))

    def boom():
        raise ConnectionError("no redis")

    monkeypatch.setattr(q, "_redis", boom)
    q.CeleryQueue().enqueue("anchor_render", {"project_id": "p1"})
    assert len(sent) == 1


async def test_inline_queue_honours_a_delay():
    seen = []

    async def fake(step, payload):
        seen.append(step)

    import app.pipeline.runner as r

    original = r.run_step
    r.run_step = fake
    try:
        inline = q.InlineQueue()
        inline.enqueue("x", {}, delay=0.05)
        await asyncio.sleep(0)
        assert seen == []
        await inline.drain()
        assert seen == ["x"]
    finally:
        r.run_step = original


# ---------- a vendor with no free slot is a place in line, not a failure ----------
async def _fresh_busy_rows(maker, pid, n=3):
    async with maker() as s:
        for i in range(n):
            s.add(ProviderRequest(project_id=pid, provider="mock", slot=f"s{i}", request_hash="x", status="submitted"))
        await s.commit()


async def test_busy_vendor_defers_the_video_instead_of_failing_it(client, workspace, maker):
    registry.override(avatar=AsyncVendor())
    rec = Recorder()
    set_queue(rec)
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme, a farm marketplace."}]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": False}, headers=OWNER)
    assert rec.calls[-1][0] == "anchor_render"
    await _fresh_busy_rows(maker, pid)

    # three busy answers in a row: more than the vendor's three attempts, yet the video is still alive
    for _ in range(4):
        rec.calls.clear()
        await runner.run_step("anchor_render", {"project_id": pid})
        assert [c[0] for c in rec.calls] == ["anchor_render"], "the job must be put back in line"
    async with maker() as s:
        p = await s.get(Project, pid)
        job = (await s.execute(select(Job).where(Job.project_id == pid, Job.stage == "anchor_render"))).scalar_one()
    assert p.state == "rendering_anchor" and job.status == "pending" and job.failure_category == "busy"

    async with maker() as s:  # a slot frees up
        for r in (await s.execute(select(ProviderRequest).where(ProviderRequest.project_id == pid))).scalars():
            r.status = "completed"
        await s.commit()
    set_queue(q.InlineQueue())
    await runner.run_step("anchor_render", {"project_id": pid})
    await q.get_queue().drain()
    async with maker() as s:
        assert (await s.get(Project, pid)).state in {"anchor_ready", "final_ready"}


async def test_a_waiting_video_is_eventually_reported_if_the_wait_is_hopeless(client, workspace, maker, monkeypatch):
    registry.override(avatar=AsyncVendor())
    set_queue(Recorder())
    monkeypatch.setattr(runner, "MAX_BUSY_WAIT", timedelta(seconds=-1))
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": False}, headers=OWNER)
    await _fresh_busy_rows(maker, pid)
    for _ in range(4):
        await runner.run_step("anchor_render", {"project_id": pid})
    async with maker() as s:
        assert (await s.get(Project, pid)).state == "failed"


# ---------- a worker is not held for the whole of a long clip ----------
async def test_a_slow_clip_frees_the_worker_and_is_resumed_not_resubmitted(client, workspace, maker, monkeypatch):
    from app.config import get_settings

    vendor = AsyncVendor()
    vendor.pending_polls = 10**9  # the vendor is slow
    registry.override(avatar=vendor)
    rec = Recorder()
    set_queue(rec)
    monkeypatch.setattr(get_settings(), "queue_backend", "celery")
    monkeypatch.setattr(get_settings(), "vendor_hold_s", 0.05)
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": False}, headers=OWNER)

    for _ in range(3):  # three visits while the vendor is still working
        rec.calls.clear()
        await runner.run_step("anchor_render", {"project_id": pid})
        assert [c[0] for c in rec.calls] == ["anchor_render"]  # back in line
    async with maker() as s:
        job = (await s.execute(select(Job).where(Job.project_id == pid, Job.stage == "anchor_render"))).scalar_one()
        p = await s.get(Project, pid)
    assert vendor.submits == 1  # one paid submission, however many visits
    assert job.status == "pending" and job.attempts == 0 and p.state == "rendering_anchor"

    vendor.pending_polls = 0  # it finishes
    monkeypatch.setattr(get_settings(), "queue_backend", "inline")
    set_queue(q.InlineQueue())
    await runner.run_step("anchor_render", {"project_id": pid})
    await q.get_queue().drain()
    async with maker() as s:
        assert (await s.get(Project, pid)).state in {"anchor_ready", "final_ready"}
    assert vendor.submits == 1


# ---------- racing workers ----------
async def test_only_one_of_many_racing_workers_claims_a_job(client, workspace, maker):
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    async with maker() as s:
        s.add(Job(id="j1", project_id=pid, stage="anchor_render", input_hash="h", status="pending"))
        await s.commit()

    async def attempt():
        async with maker() as s:
            return await runner._claim(s, "j1", timedelta(minutes=20))

    results = await asyncio.gather(*(attempt() for _ in range(6)))
    assert results.count(True) == 1


async def test_a_job_whose_owner_is_long_gone_can_be_taken_over(client, workspace, maker):
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    long_ago = datetime.now(UTC) - timedelta(hours=2)
    async with maker() as s:
        s.add(
            Job(id="j2", project_id=pid, stage="anchor_render", input_hash="h", status="running", started_at=long_ago)
        )
        await s.commit()
    async with maker() as s:
        assert await runner._claim(s, "j2", timedelta(minutes=20))
    async with maker() as s:  # now fresh: nobody else may take it
        assert not await runner._claim(s, "j2", timedelta(minutes=20))


async def test_racing_submissions_never_exceed_the_vendor_limit(client, workspace, maker):
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    async with maker() as s:
        ids = []
        for i in range(6):
            r = ProviderRequest(project_id=pid, provider="mock", slot=f"s{i}", request_hash="x")
            s.add(r)
            await s.flush()
            ids.append(r.id)
        await s.commit()
    policy = VendorPolicy(max_concurrency=2)

    async def take(i):
        try:
            await provider_requests._take_slot(i, "mock", policy)
            return True
        except ProviderError as e:
            assert e.category == "busy"
            return False

    got = await asyncio.gather(*(take(i) for i in ids))
    assert got.count(True) == 2


async def test_rows_left_behind_by_dead_projects_do_not_hold_slots_for_ever(client, workspace, maker):
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    old = datetime.now(UTC) - timedelta(hours=5)
    async with maker() as s:
        for i in range(3):  # three "in flight" requests from long ago: their projects were cancelled or abandoned
            s.add(
                ProviderRequest(
                    project_id=pid,
                    provider="mock",
                    slot=f"s{i}",
                    request_hash="x",
                    status="submitted",
                    vendor_video_id=f"v{i}",
                    submitted_at=old,
                )
            )
        r = ProviderRequest(project_id=pid, provider="mock", slot="new", request_hash="y")
        s.add(r)
        await s.flush()
        rid = r.id
        await s.commit()
    await provider_requests._take_slot(rid, "mock", VendorPolicy(max_concurrency=3))  # does not raise


# ---------- the renderer restarted ----------
async def test_a_restarted_renderer_is_a_retry_not_a_failed_video():
    r = HttpRenderer()
    r._client = httpx.AsyncClient(
        base_url="http://r", transport=httpx.MockTransport(lambda req: httpx.Response(404, json={"error": "not found"}))
    )
    with pytest.raises(ProviderError) as e:
        await r.status("gone")
    assert e.value.category == "temporary" and e.value.retryable
    with pytest.raises(ProviderError):
        await r._job("gone")


async def test_waiting_on_a_stuck_render_gives_up(monkeypatch):
    from app.integrations.renderer.base import RenderStatus
    from app.pipeline import steps

    cancelled = []

    class Stuck:
        async def status(self, rid):
            return RenderStatus("running", 0.1, [], None)

        async def cancel(self, rid):
            cancelled.append(rid)

    monkeypatch.setitem(steps.VENDOR_POLICIES, "renderer", VendorPolicy(timeout_s=0))
    with pytest.raises(TimeoutError):
        await steps._wait(Stuck(), "r1")
    assert cancelled == ["r1"]


# ---------- readiness ----------
async def test_readiness_reports_the_queue(client, maker, monkeypatch):
    from app.config import get_settings

    async def depths():
        return {"interactive": 0, "avatar": 3, "render": 1, "default": 0}

    monkeypatch.setattr(get_settings(), "queue_backend", "celery")
    monkeypatch.setattr(q, "lane_depths", depths)
    r = (await client.get("/health/ready")).json()
    assert r["checks"]["queue"] == "ok" and r["queue_depth"]["avatar"] == 3
