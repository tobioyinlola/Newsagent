"""The durable line for presenter clips and renders (QUEUE_MODE=dispatcher): order, fairness, capacity, crash recovery."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.config import get_settings
from app.models import Job, Project, SystemSetting, WorkItem, Workspace
from app.models.base import new_id
from app.pipeline.queue import Queue, set_queue
from app.services import work_queue
from tests.conftest import OPS, OWNER
from tests.helpers import BRIEF


class Recorder(Queue):
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def enqueue(self, step, payload, delay=0.0):
        self.calls.append((step, payload["project_id"]))

    @property
    def projects(self):
        return [p for _, p in self.calls]


@pytest.fixture
def rec():
    r = Recorder()
    set_queue(r)
    return r


@pytest.fixture
def line(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "queue_mode", "dispatcher")
    monkeypatch.setattr(s, "render_queue_slots", 2)
    return s


async def _ws(maker, name="Biz") -> str:
    async with maker() as s:
        ws = Workspace(name=name, credit_balance=Decimal("0"))
        s.add(ws)
        await s.commit()
        return ws.id


async def _project(maker, ws: str, state="anchor_ready") -> str:
    async with maker() as s:
        p = Project(id=new_id(), workspace_id=ws, state=state, state_changed_at=datetime.now(UTC))
        s.add(p)
        await s.commit()
        return p.id


async def _join(maker, step, pid):
    async with maker() as s:
        await work_queue.submit(s, step, pid)


async def _finish(maker, pid, state="final_ready"):
    async with maker() as s:
        await s.execute(update(Project).where(Project.id == pid).values(state=state))
        await s.commit()


async def test_with_the_line_off_work_goes_straight_to_the_workers(maker, rec):
    pid = await _project(maker, await _ws(maker))
    await _join(maker, "final_render", pid)
    assert rec.calls == [("final_render", pid)]
    async with maker() as s:
        assert (await s.execute(select(WorkItem))).first() is None


async def test_videos_are_taken_in_the_order_they_joined_and_only_as_fast_as_capacity_frees(maker, rec, line):
    pids = [await _project(maker, await _ws(maker, f"b{i}")) for i in range(5)]
    for pid in pids:
        await _join(maker, "final_render", pid)
        await asyncio.sleep(0.01)
    assert rec.projects == pids[:2]  # two renderer slots
    await _finish(maker, pids[0])
    await work_queue.dispatch_once()
    assert rec.projects == pids[:3]  # the next in line, not a later one
    await _finish(maker, pids[1])
    await _finish(maker, pids[2])
    await work_queue.dispatch_once()
    assert rec.projects == pids  # everyone was taken, in order


async def test_one_business_cannot_take_every_slot(maker, rec, line):
    big = await _ws(maker, "big")
    small = await _ws(maker, "small")
    a, b, c = [await _project(maker, big) for _ in range(3)]
    s1 = await _project(maker, small)
    for pid in (a, b, c, s1):
        await _join(maker, "final_render", pid)
        await asyncio.sleep(0.01)
    assert rec.projects == [a, s1]  # the big business's second video waits although a slot is free
    await _finish(maker, a)
    await work_queue.dispatch_once()
    assert rec.projects == [a, s1, b]


async def test_a_video_keeps_its_place_when_it_moves_to_its_next_step(maker, rec, line):
    ws1, ws2, ws3 = await _ws(maker, "1"), await _ws(maker, "2"), await _ws(maker, "3")
    first, second, third = [await _project(maker, w) for w in (ws1, ws2, ws3)]
    await _join(maker, "preview_render", first)
    await asyncio.sleep(0.01)
    await _join(maker, "preview_render", second)
    await asyncio.sleep(0.01)
    await _join(maker, "final_render", third)  # joins later; both slots are taken by the first two
    assert rec.projects == [first, second]
    async with maker() as s:
        original = (await s.execute(select(WorkItem.enqueued_at).where(WorkItem.project_id == first))).scalar_one()
    await _join(maker, "final_render", first)  # the preview finished; its final render is next
    async with maker() as s:
        it = (await s.execute(select(WorkItem).where(WorkItem.project_id == first))).scalar_one()
        assert it.step == "final_render" and it.enqueued_at == original  # same place in line as when it first joined
    # the slot it gave up goes to the oldest waiting video, which is this one (the third joined later)
    assert rec.calls == [("preview_render", first), ("preview_render", second), ("final_render", first)]


async def test_finished_cancelled_and_failed_videos_leave_the_line(maker, rec, line):
    ws = [await _ws(maker, str(i)) for i in range(4)]
    a, b, c, d = [await _project(maker, w) for w in ws]
    for pid in (a, b, c, d):
        await _join(maker, "final_render", pid)
    await _finish(maker, c, "cancelled")
    await _finish(maker, d, "failed")
    await work_queue.dispatch_once()
    async with maker() as s:
        left = set((await s.execute(select(WorkItem.project_id))).scalars())
    assert left == {a, b}


async def test_a_released_job_whose_worker_died_goes_back_in_line_at_its_place(maker, rec, line, monkeypatch):
    monkeypatch.setattr(get_settings(), "render_queue_slots", 1)
    a, b = [await _project(maker, await _ws(maker, n)) for n in "ab"]
    await _join(maker, "final_render", a)
    await asyncio.sleep(0.01)
    await _join(maker, "final_render", b)
    assert rec.projects == [a]
    monkeypatch.setattr(get_settings(), "queue_dispatch_grace_s", 0)
    await work_queue.dispatch_once()  # nothing is running a: no job row, no sign of life
    assert rec.projects == [a, a]  # back in line first, released again, before b
    async with maker() as s:
        it = (await s.execute(select(WorkItem).where(WorkItem.project_id == a))).scalar_one()
        assert it.attempts == 1
    # a job that is alive (a heartbeat inside its lease) is left alone
    async with maker() as s:
        s.add(Job(project_id=a, stage="final_render", input_hash="x", status="running", started_at=datetime.now(UTC)))
        await s.commit()
    await work_queue.dispatch_once()
    assert rec.projects == [a, a]


async def test_a_paused_lane_holds_its_line_and_releases_it_again(maker, rec, line):
    pid = await _project(maker, await _ws(maker))
    async with maker() as s:
        await work_queue.set_lane_paused(s, "render", True, "ops")
    await _join(maker, "final_render", pid)
    assert rec.calls == []  # it waits; it does not fail
    async with maker() as s:
        assert (await s.get(Project, pid)).state == "anchor_ready"
        await work_queue.set_lane_paused(s, "render", False, "ops")
    await work_queue.dispatch_once()
    assert rec.projects == [pid]


async def test_the_emergency_pause_holds_the_line_instead_of_failing_everyone(maker, rec, line):
    async with maker() as s:
        s.add(SystemSetting(key="paid_steps_paused", value={"paused": True}))
        await s.commit()
    pid = await _project(maker, await _ws(maker))
    await _join(maker, "final_render", pid)
    assert rec.calls == []


async def test_an_operator_can_move_a_video_to_the_front(maker, rec, line, monkeypatch):
    monkeypatch.setattr(get_settings(), "render_queue_slots", 1)
    pids = [await _project(maker, await _ws(maker, str(i))) for i in range(3)]
    for pid in pids:
        await _join(maker, "final_render", pid)
        await asyncio.sleep(0.01)
    async with maker() as s:
        assert await work_queue.move_to_front(s, pids[2]) is True
        assert await work_queue.move_to_front(s, pids[0]) is False  # already running
    await _finish(maker, pids[0])
    await work_queue.dispatch_once()
    assert rec.projects == [pids[0], pids[2]]


async def test_position_and_estimate_for_a_waiting_video(maker, rec, line, monkeypatch):
    monkeypatch.setattr(get_settings(), "render_queue_slots", 2)
    pids = [await _project(maker, await _ws(maker, str(i))) for i in range(6)]
    for pid in pids:
        await _join(maker, "final_render", pid)
        await asyncio.sleep(0.01)
    async with maker() as s:
        assert (await work_queue.position_of(s, pids[0]))["state"] == "running"
        third = await work_queue.position_of(s, pids[2])
        assert (
            third["state"] == "waiting" and third["position"] == 1 and third["eta_seconds"] is None
        )  # not enough finished yet
        for i in range(3):  # three recent renders took 20 minutes each
            s.add(
                Job(
                    project_id=pids[0],
                    stage="final_render",
                    input_hash=f"h{i}",
                    status="succeeded",
                    duration_s=Decimal("1200"),
                )
            )
        await s.commit()
        sixth = await work_queue.position_of(s, pids[5])
        assert sixth["position"] == 4 and sixth["eta_seconds"] == 2 * 1200  # four in front, two at a time
        summary = {x["lane"]: x for x in await work_queue.lane_summary(s)}
        assert (
            summary["render"]["waiting"] == 4 and summary["render"]["running"] == 2 and summary["render"]["slots"] == 2
        )


async def test_two_thousand_videos_are_all_taken_in_order_without_exceeding_capacity(maker, rec, line, monkeypatch):
    """2000 videos join at the same moment. Presenter clips run 8 at a time; none is lost, repeated, refused or taken out of order."""
    from app.config import VENDOR_POLICIES

    monkeypatch.setitem(VENDOR_POLICIES, "avatar", VENDOR_POLICIES["avatar"].model_copy(update={"max_concurrency": 8}))
    n = 2000
    base = datetime.now(UTC) - timedelta(hours=1)
    pids = []
    async with maker() as s:
        for i in range(n):
            p = Project(id=new_id(), workspace_id=f"ws{i}", state="rendering_anchor", state_changed_at=base)
            s.add(p)
            pids.append(p.id)
        await s.flush()
        for i, pid in enumerate(pids):
            s.add(
                WorkItem(
                    project_id=pid,
                    workspace_id=f"ws{i}",
                    lane="avatar",
                    step="anchor_render",
                    enqueued_at=base + timedelta(seconds=i),
                )
            )
        await s.commit()
    peak = 0
    while len(rec.calls) < n:
        before = len(rec.calls)
        await work_queue.dispatch_once()
        async with maker() as s:
            running = list((await s.execute(select(WorkItem.project_id).where(WorkItem.state == "running"))).scalars())
        peak = max(peak, len(running))
        assert len(running) <= 8
        assert len(rec.calls) > before or running  # always progress
        for pid in running:
            await _finish(maker, pid, "anchor_ready")
    assert rec.projects == pids  # exactly once each, in the order they joined
    assert peak == 8


async def test_waiting_in_line_never_turns_into_a_failure(line):
    assert work_queue.max_busy_wait() == timedelta(hours=36)


async def test_the_old_wait_limit_still_applies_when_the_line_is_off(monkeypatch):
    assert work_queue.max_busy_wait() == timedelta(hours=3)


async def test_the_stuck_project_sweep_leaves_videos_in_line_to_the_dispatcher(maker, rec, line):
    from app.jobs import reconcile_projects

    pid = await _project(maker, await _ws(maker))
    async with maker() as s:
        await s.execute(
            update(Project).where(Project.id == pid).values(state_changed_at=datetime.now(UTC) - timedelta(hours=5))
        )
        s.add(WorkItem(project_id=pid, workspace_id="w", lane="render", step="final_render", state="waiting"))
        await s.commit()
    assert await reconcile_projects() == 0


async def test_a_customer_sees_their_place_in_line_and_an_operator_can_stop_a_video(
    client, maker, workspace, rec, line, monkeypatch
):
    monkeypatch.setattr(get_settings(), "render_queue_slots", 1)
    pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    other_ws = await _ws(maker, "Other")
    async with maker() as s:
        await s.execute(
            update(Project).where(Project.id == pid).values(state="anchor_ready", state_changed_at=datetime.now(UTC))
        )
        other = Project(
            id=new_id(),
            workspace_id=other_ws,
            state="anchor_ready",
            state_changed_at=datetime.now(UTC),
        )
        s.add(other)
        await s.commit()
        other_id = other.id
    await _join(maker, "final_render", other_id)  # takes the only slot
    await _join(maker, "final_render", pid)
    progress = (await client.get(f"/v1/projects/{pid}/progress", headers=OWNER)).json()
    assert progress["line"]["state"] == "waiting" and progress["line"]["position"] == 1

    board = (await client.get("/v1/admin/queue", headers=OPS)).json()
    assert {x["lane"] for x in board["lanes"]} == {"avatar", "render"}
    assert next(x for x in board["lanes"] if x["lane"] == "render")["waiting"] == 1
    items = (await client.get("/v1/admin/line", headers=OPS)).json()
    assert [i["project_id"] for i in items if i["lane"] == "render"] == [other_id, pid]

    assert (await client.post(f"/v1/admin/line/{pid}/cancel", headers=OPS)).status_code == 200
    async with maker() as s:
        assert (await s.get(Project, pid)).state == "cancelled"
        assert (await s.execute(select(WorkItem).where(WorkItem.project_id == pid))).first() is None
    assert (await client.post("/v1/admin/line/lanes/render/pause", json={"paused": True}, headers=OPS)).json()[
        "paused"
    ] is True
    assert (await client.get("/v1/admin/queue", headers=OPS)).json()["lanes"][1]["paused"] is True
    assert (await client.post("/v1/admin/line/lanes/nope/pause", json={"paused": True}, headers=OPS)).status_code == 404
    assert (await client.get("/v1/admin/line", headers=OWNER)).status_code in {401, 403}


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs Postgres (the advisory lock)")
async def test_two_dispatchers_at_once_never_release_more_than_capacity(maker, rec, line):
    pids = [await _project(maker, await _ws(maker, str(i))) for i in range(12)]
    async with maker() as s:
        for i, pid in enumerate(pids):
            s.add(WorkItem(project_id=pid, workspace_id=f"w{i}", lane="render", step="final_render"))
        await s.commit()
    await asyncio.gather(*(work_queue.dispatch_once() for _ in range(6)))
    assert len(rec.calls) == 2 and len(set(rec.projects)) == 2
