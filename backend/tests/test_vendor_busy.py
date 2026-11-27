import httpx
import pytest

from app.integrations import errors, registry
from app.services import notifications
from tests.conftest import OWNER
from tests.test_guided_flow import DETAILS


def response(code, body=None, headers=None):
    return httpx.Response(code, json=body or {}, headers=headers or {}, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


def refused(code, body=None, headers=None):
    return httpx.HTTPStatusError("x", request=httpx.Request("POST", "https://x"), response=response(code, body, headers))


def test_too_fast_is_retried_but_no_credit_is_not():
    fast = errors.classify(refused(429, {"error": {"code": "rate_limit_exceeded", "type": "requests"}}, {"retry-after": "7"}))
    assert (fast.category, fast.retryable, fast.retry_after) == ("rate_limited", True, 7.0)
    broke = errors.classify(refused(429, {"error": {"code": "insufficient_quota", "type": "insufficient_quota"}}))
    assert (broke.category, broke.retryable) == ("quota", False)
    assert errors.classify(refused(429, None)).category == "rate_limited"  # a body we cannot read: assume it is only busy


@pytest.fixture
def llm_says(monkeypatch):
    def set_up(exc):
        llm = registry.get_llm()

        async def boom(*a, **k):
            raise exc

        monkeypatch.setattr(type(llm), "parse_brief", boom, raising=False)

    return set_up


async def start_guided(client):
    pid = (await client.post("/v1/projects", json=DETAILS, headers=OWNER)).json()["id"]
    return pid, await client.post(f"/v1/projects/{pid}/guided/start", headers=OWNER)


async def test_a_busy_writer_gives_a_calm_try_again_not_a_crash(client, workspace, llm_says):
    llm_says(refused(429, {"error": {"code": "rate_limit_exceeded"}}, {"retry-after": "12"}))
    pid, r = await start_guided(client)
    assert r.status_code == 503 and "try again in a minute" in r.json()["detail"] and "Nothing was lost" in r.json()["detail"]
    assert r.headers["retry-after"] == "12"
    # the draft is still there, so trying again works
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).status_code == 200


async def test_out_of_credit_tells_the_operators_once(client, workspace, llm_says, monkeypatch):
    told = []

    async def note(subject, text):
        told.append(subject)

    monkeypatch.setattr(notifications, "notify_operators", note)
    errors._last_alert.clear()
    llm_says(refused(429, {"error": {"code": "insufficient_quota"}}))
    for _ in range(2):
        _, r = await start_guided(client)
        assert r.status_code == 503 and "unavailable for a short while" in r.json()["detail"] and r.headers["retry-after"] == "300"
    import asyncio

    await asyncio.sleep(0.05)
    assert len(told) == 1 and "writing provider" in told[0]  # not an email per customer


async def test_a_real_bug_is_still_an_error(client, workspace, llm_says):
    llm_says(KeyError("bug"))
    _, r = await start_guided(client)
    assert r.status_code == 500
