import httpx

from app.integrations.email.resend import ResendEmail


async def test_resend_posts_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), request.read()
        return httpx.Response(200, json={"id": "x"})

    client = httpx.AsyncClient(base_url="https://api.resend.com", transport=httpx.MockTransport(handler))
    await ResendEmail(client).send("a@example.com", "Hi", "plain")
    assert seen["url"] == "https://api.resend.com/emails"
    assert b'"to":["a@example.com"]' in seen["body"].replace(b" ", b"")


def _client(handler):
    return httpx.AsyncClient(base_url="https://api.resend.com", transport=httpx.MockTransport(handler))


async def test_a_rate_limited_email_is_tried_again_after_the_wait_the_provider_asks_for(monkeypatch):
    import pytest

    from app.integrations.email import resend as r

    waits: list[float] = []

    async def fake_sleep(s):
        waits.append(s)

    monkeypatch.setattr(r, "_sleep", fake_sleep)
    monkeypatch.setattr(r, "_next_slot", 0.0)
    calls = []

    def handler(request):
        calls.append(1)
        return (
            httpx.Response(429, headers={"retry-after": "3"}, json={"message": "slow down"})
            if len(calls) < 3
            else httpx.Response(200, json={"id": "x"})
        )

    await ResendEmail(_client(handler)).send("a@example.com", "Hi", "plain")
    assert (
        len(calls) == 3 and 3.0 in waits
    )  # two refusals, then it went through; it waited the 3 seconds it was told to

    # a provider that keeps failing is given up on after the configured number of tries, and the error still reaches the caller
    calls.clear()
    with pytest.raises(httpx.HTTPStatusError):
        await ResendEmail(_client(lambda req: (calls.append(1), httpx.Response(503, json={}))[1])).send(
            "a@example.com", "Hi", "plain"
        )
    assert len(calls) == 5

    # a refusal that retrying cannot fix (a bad request, an unverified domain) is not retried
    calls.clear()
    with pytest.raises(httpx.HTTPStatusError):
        await ResendEmail(_client(lambda req: (calls.append(1), httpx.Response(422, json={}))[1])).send(
            "a@example.com", "Hi", "plain"
        )
    assert len(calls) == 1


async def test_a_dropped_connection_is_retried(monkeypatch):
    from app.integrations.email import resend as r

    async def no_wait(s):
        return None

    monkeypatch.setattr(r, "_sleep", no_wait)
    monkeypatch.setattr(r, "_next_slot", 0.0)
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ConnectError("reset")
        return httpx.Response(200, json={"id": "x"})

    await ResendEmail(_client(handler)).send("a@example.com", "Hi", "plain")
    assert len(calls) == 2


async def test_a_burst_of_emails_is_spread_out(monkeypatch):
    import asyncio

    from app.config import get_settings
    from app.integrations.email import resend as r

    waits: list[float] = []

    async def fake_sleep(s):
        waits.append(s)

    monkeypatch.setattr(r, "_sleep", fake_sleep)
    monkeypatch.setattr(r, "_next_slot", 0.0)
    monkeypatch.setattr(get_settings(), "email_max_per_second", 10.0)
    sender = ResendEmail(_client(lambda req: httpx.Response(200, json={"id": "x"})))
    await asyncio.gather(*(sender.send(f"u{i}@example.com", "Hi", "plain") for i in range(5)))
    assert len(waits) == 4 and all(0.05 < w < 0.6 for w in waits)  # each later send waits another tenth of a second
    assert sorted(waits)[-1] > sorted(waits)[0] + 0.25
