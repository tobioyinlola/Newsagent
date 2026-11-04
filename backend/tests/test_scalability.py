"""Safe scale-ups: work that used to block the API's single event loop or hold a database connection now does neither."""

import asyncio
import threading
import time

from app.services import passwords


async def test_password_hashing_runs_off_the_event_loop_and_is_capped(monkeypatch):
    main = threading.get_ident()
    running, peak, threads = 0, 0, set()
    lock = threading.Lock()

    def slow(password: str) -> str:
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
            threads.add(threading.get_ident())
        time.sleep(0.05)
        with lock:
            running -= 1
        return "hash:" + password

    monkeypatch.setattr(passwords, "hash_password", slow)
    out = await asyncio.gather(*(passwords.hash_password_async(f"p{i}") for i in range(12)))
    assert out == [f"hash:p{i}" for i in range(12)]
    assert main not in threads  # never on the event loop's own thread
    assert peak <= 4  # and never more than four at once (each takes ~32 MiB)


async def test_the_awaitable_helpers_give_the_same_answers_as_the_plain_ones():
    stored = await passwords.hash_password_async("correct horse battery")
    assert stored.startswith("scrypt$") and passwords.verify_password("correct horse battery", stored)
    assert await passwords.verify_password_async("correct horse battery", stored) is True
    assert await passwords.verify_password_async("wrong password!", stored) is False
    assert (
        await passwords.verify_password_async("anything", None) is False
    )  # an unknown email still costs one derivation


async def test_release_connection_only_lets_go_when_nothing_is_unsaved(maker):
    from sqlalchemy import select, text

    from app.db import release_connection
    from app.models import Workspace

    async with maker() as s:
        await s.execute(text("select 1"))
        assert s.in_transaction()
        await release_connection(s)
        assert not s.in_transaction()  # the connection went back to the pool

    async with maker() as s:
        ws = Workspace(name="Release Co")
        s.add(ws)  # unsaved work: it must not be committed early
        await release_connection(s)
        assert s.in_transaction() and ws in s.new
        await s.rollback()
    async with maker() as s:
        assert (await s.execute(select(Workspace).where(Workspace.name == "Release Co"))).first() is None


async def test_the_ai_writer_is_never_called_while_a_database_connection_is_held(client, workspace, monkeypatch):
    """Starting the interview, producing the story and writing a press release all wait on the AI writer for a while. None of them may
    sit on one of the few pooled database connections while they do."""
    from app.services import guided
    from tests.conftest import OWNER
    from tests.test_guided_flow import interviewed

    seen: list[bool] = []
    real = guided.release_connection

    async def spy(session):
        await real(session)
        seen.append(session.in_transaction())

    monkeypatch.setattr(guided, "release_connection", spy)
    pid = await interviewed(client)  # the details step starts the interview (one release)
    assert (
        await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    ).status_code == 200  # produce the story (another)
    assert len(seen) >= 2 and not any(seen)

    from app.services import press_release

    monkeypatch.setattr(press_release, "release_connection", spy)
    body = {
        "kind": "other",
        "details": "Acme Farms opened a new packing house in Kumasi to serve more farmers.",
        "first_name": "Ada",
        "last_name": "Obi",
        "role": "CEO",
        "company": "ACME",
        "city": "KUMASI",
        "country": "GHANA",
    }
    before = len(seen)
    assert (await client.post("/v1/distribution/press-release", json=body, headers=OWNER)).status_code == 200
    assert len(seen) == before + 1 and not seen[-1]
