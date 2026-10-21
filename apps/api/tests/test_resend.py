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
