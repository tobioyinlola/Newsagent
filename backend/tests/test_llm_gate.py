"""A rush of writing calls waits its turn and retries a busy provider, instead of all arriving at once and failing."""

import asyncio

import httpx
import pytest

from app.config import get_settings
from app.integrations.llm import gate
from app.integrations.llm.json_llm import JsonScriptLLM


class Fake(JsonScriptLLM):
    def __init__(self, fail_first=0, status=429):
        self.fail_first, self.status, self.calls, self.running, self.peak = fail_first, status, 0, 0, 0

    async def _complete(self, prompt: str) -> str:
        self.calls += 1
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            await asyncio.sleep(0.01)
            if self.calls <= self.fail_first:
                req = httpx.Request("POST", "http://x")
                raise httpx.HTTPStatusError("busy", request=req, response=httpx.Response(self.status, request=req))
            return '{"ok": true}'
        finally:
            self.running -= 1


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    async def no_sleep(_):
        return None

    monkeypatch.setattr(gate.asyncio, "sleep", no_sleep)


async def test_a_rush_never_has_more_calls_in_flight_than_the_limit(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_max_concurrency", 4)
    llm = Fake()

    async def slow(prompt):  # a real sleep, so calls overlap
        llm.running += 1
        llm.peak = max(llm.peak, llm.running)
        await asyncio.get_running_loop().run_in_executor(None, lambda: None)
        await asyncio.sleep(0)
        llm.running -= 1
        return '{"ok": true}'

    llm._complete = slow  # type: ignore[method-assign]
    out = await asyncio.gather(*(llm._json("p") for _ in range(50)))
    assert out == [{"ok": True}] * 50
    assert llm.peak <= 4


async def test_a_busy_provider_is_asked_again_and_the_customer_never_sees_it():
    llm = Fake(fail_first=2, status=429)
    assert await llm._json("p") == {"ok": True}
    assert llm.calls == 3


async def test_a_refusal_is_not_retried(monkeypatch):
    llm = Fake(fail_first=5, status=400)
    with pytest.raises(httpx.HTTPStatusError):
        await llm._json("p")
    assert llm.calls == 1


async def test_it_gives_up_after_the_retries(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_retries", 1)
    llm = Fake(fail_first=9, status=503)
    with pytest.raises(httpx.HTTPStatusError):
        await llm._json("p")
    assert llm.calls == 2
