"""Which browser origins may call the API."""

from app.config import get_settings

LOGIN = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}


async def test_an_unlisted_site_is_refused_and_a_site_matching_the_configured_pattern_is_allowed(client, monkeypatch):
    other = {"Origin": "https://newsagent-git-staging-team.vercel.app", **LOGIN}
    assert (
        await client.options("/v1/auth/login", headers=other)
    ).status_code == 400  # the browser sees "Failed to fetch"
    monkeypatch.setattr(get_settings(), "cors_origin_regex", r"https://newsagent-[a-z0-9-]+-team\.vercel\.app")
    import httpx

    from app.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        r = await c.options("/v1/auth/login", headers=other)
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == other["Origin"]
        evil = {"Origin": "https://newsagent-git-staging-other.vercel.app", **LOGIN}
        assert (await c.options("/v1/auth/login", headers=evil)).status_code == 400
