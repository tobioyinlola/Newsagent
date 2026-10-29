"""Load test for the whole video pipeline, through the real API, queue and workers (vendors are simulated).

Run the stack with USE_MOCKS=true, MOCK_VENDOR_LATENCY_S=<seconds a clip/render takes>, QUEUE_BACKEND=celery, ENFORCE_LIMITS=false,
on a THROWAWAY database and Redis db. NEVER point this at real vendor keys: it makes N videos. See docs/queueing.md.

    python scripts/loadtest_pipeline.py --videos 60 --workspaces 20 --api http://localhost:8000

Needs the backend's environment (DATABASE_URL, REDIS_URL) to seed workspaces and to sample the queue.
Prints how long videos took from "approve" to "ready", how many failed, the deepest each lane got, peak DB connections, and the API's
own response times while the load ran.
"""

import argparse
import asyncio
import statistics
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import session_maker  # noqa: E402
from app.models import Base, User, Workspace  # noqa: E402
from app.pipeline.queue import lane_depths  # noqa: E402
from app.services import ledger  # noqa: E402

BRIEF = "Acme helps farmers sell produce online across Nigeria and Ghana. We launched a marketplace that connects 500 farmers to buyers."


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else 0.0


async def seed(n: int) -> list[str]:
    async with session_maker()() as s:
        emails = []
        for i in range(n):
            ws = Workspace(name=f"Load {i}", credit_balance=Decimal("0"))
            s.add(ws)
            await s.flush()
            await ledger.apply(s, ws, Decimal("1000"), "grant", description="load test")
            email = f"load{i}-{int(time.time())}@loadtest.test"
            s.add(User(email=email, workspace_id=ws.id))
            emails.append(email)
        await s.commit()
    return emails


async def one_video(c: httpx.AsyncClient, email: str, lat: list[float], results: list[dict], timeout: float) -> None:
    h = {"Authorization": f"Bearer dev:{email}"}
    rec = {"state": "?", "seconds": None, "error": None}
    results.append(rec)
    try:
        t = time.monotonic()
        pid = (await c.post("/v1/projects", json={"brief_text": BRIEF}, headers=h)).json()["id"]
        lat.append(time.monotonic() - t)
        r = await c.post(f"/v1/projects/{pid}/script/generate", headers=h)
        r.raise_for_status()
        r = await c.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": False}, headers=h)
        r.raise_for_status()
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            t = time.monotonic()
            st = (await c.get(f"/v1/projects/{pid}", headers=h)).json()
            lat.append(time.monotonic() - t)
            rec["state"] = st["state"]
            if st["state"] in {"final_ready", "failed", "cancelled", "limit_reached"}:
                rec["seconds"] = time.monotonic() - start
                rec["error"] = st.get("failure_reason")
                return
            await asyncio.sleep(2)
        rec["error"] = "timed out waiting"
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"[:200]


async def sampler(stop: asyncio.Event, depth: dict, conns: list[int]) -> None:
    while not stop.is_set():
        try:
            for lane, n in (await lane_depths()).items():
                depth[lane] = max(depth.get(lane, 0), n)
            async with session_maker()() as s:
                conns.append((await s.execute(text("select count(*) from pg_stat_activity where datname = current_database()"))).scalar_one())
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(1)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", type=int, default=30)
    ap.add_argument("--workspaces", type=int, default=10)
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--timeout", type=float, default=1800)
    ap.add_argument("--create-tables", action="store_true", help="create the schema first (a fresh throwaway database)")
    a = ap.parse_args()
    s = get_settings()
    if not s.use_mocks or s.mock_vendor_latency_s <= 0 or s.queue_backend != "celery":
        sys.exit("refusing to run: need USE_MOCKS=true, MOCK_VENDOR_LATENCY_S>0 and QUEUE_BACKEND=celery in this environment")
    if a.create_tables:
        from app.db import session_maker as sm

        async with sm()() as sess:
            await (await sess.connection()).run_sync(Base.metadata.create_all)
            await sess.commit()
    emails = await seed(a.workspaces)
    lat: list[float] = []
    results: list[dict] = []
    depth: dict[str, int] = {}
    conns: list[int] = []
    stop = asyncio.Event()
    async with httpx.AsyncClient(base_url=a.api, timeout=60, limits=httpx.Limits(max_connections=200)) as c:
        task = asyncio.create_task(sampler(stop, depth, conns))
        t0 = time.monotonic()
        await asyncio.gather(*(one_video(c, emails[i % len(emails)], lat, results, a.timeout) for i in range(a.videos)))
        wall = time.monotonic() - t0
        stop.set()
        await task
    done = [r["seconds"] for r in results if r["state"] == "final_ready"]
    bad = [r for r in results if r["state"] != "final_ready"]
    print(f"\nvideos {a.videos} in {a.workspaces} workspaces; wall time {wall:.0f}s; vendor latency {s.mock_vendor_latency_s}s per clip/render")
    print(f"ready {len(done)}  not ready {len(bad)}  ({100 * len(done) / max(1, a.videos):.0f}% success)")
    if done:
        print(f"approve -> ready: p50 {pct(done, .5):.0f}s  p95 {pct(done, .95):.0f}s  max {max(done):.0f}s  mean {statistics.mean(done):.0f}s")
        print(f"throughput: {len(done) / wall * 60:.1f} videos/minute")
    print(f"deepest queue per lane: {depth}")
    print(f"peak database connections: {max(conns) if conns else '?'}")
    print(f"API response time while loaded ({len(lat)} calls): p50 {pct(lat, .5) * 1000:.0f}ms  p95 {pct(lat, .95) * 1000:.0f}ms  max {max(lat) * 1000:.0f}ms")
    for r in bad[:10]:
        print("  not ready:", r["state"], r["error"])
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
