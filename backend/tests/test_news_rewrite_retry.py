import httpx

from app.integrations import errors, registry
from app.integrations.llm.base import NewsDraft, NewsScene
from tests.conftest import OPS
from tests.test_news_desk import BASE, ready


def draft(body_words, script_words):
    script = " ".join(["word"] * script_words)
    return NewsDraft(
        headline="A fine headline for the story",
        summary="A short summary of what happened.",
        body=" ".join(["body"] * body_words),
        presenter_script=script,
        scenes=[NewsScene(narration=script, image_hint="An image", duration_s=20)],
    )


async def rewrite(client, row):
    return await client.post(f"{BASE}/{row['id']}/rewrite", headers=OPS, json={"revision": row["revision"]})


async def test_a_rewrite_that_misses_the_length_rules_is_asked_again_with_the_reason(client, workspace, monkeypatch):
    row = await ready(client)
    asked = []

    async def writer(self_or_text, *args):
        asked.append(args[-1] if args else "")
        return draft(150, 70) if len(asked) == 1 else draft(240, 75)  # too short, then right

    monkeypatch.setattr(type(registry.get_llm()), "write_news", lambda self, text, name, why="": writer(text, name, why))
    r = await rewrite(client, row)
    assert r.status_code == 200, r.text
    assert len(asked) == 2 and asked[0] == "" and "200" in asked[1] and "150" in asked[1]  # the second try was told the count and the rule
    assert len(r.json()["data"]["body"].split()) == 240


async def test_a_writer_that_keeps_missing_says_why_after_three_tries(client, workspace, monkeypatch):
    row = await ready(client)
    calls = []

    async def always_short(self, text, name, why=""):
        calls.append(why)
        return draft(120, 70)

    monkeypatch.setattr(type(registry.get_llm()), "write_news", always_short)
    r = await rewrite(client, row)
    assert r.status_code == 502 and "kept missing" in r.json()["detail"] and "120" in r.json()["detail"]
    assert len(calls) == 3
    assert (await client.get(f"{BASE}/{row['id']}", headers=OPS)).json()["data"] == row["data"]  # the saved draft is untouched


async def test_a_busy_provider_is_a_calm_try_again_not_a_bad_gateway(client, workspace, monkeypatch):
    row = await ready(client)

    async def busy(self, text, name, why=""):
        raise httpx.HTTPStatusError("x", request=httpx.Request("POST", "https://x"), response=httpx.Response(429, json={"error": {"code": "rate_limit_exceeded"}}, headers={"retry-after": "9"}, request=httpx.Request("POST", "https://x")))

    monkeypatch.setattr(type(registry.get_llm()), "write_news", busy)
    errors._last_alert.clear()
    r = await rewrite(client, row)
    assert r.status_code == 503 and "very busy" in r.json()["detail"] and r.headers["retry-after"] == "9"
