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
