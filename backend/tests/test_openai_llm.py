"""The writing jobs through an OpenAI-compatible endpoint (no network: the HTTP call is faked)."""

import json

import httpx

from app.config import get_settings
from app.integrations.llm.json_llm import parse_json_object
from app.integrations.llm.openai import OpenAIScriptLLM


def fake_client(reply: dict | str, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        text = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    return httpx.AsyncClient(base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handler))


def test_a_json_object_is_found_inside_prose_or_a_code_fence():
    assert parse_json_object('Here you go:\n```json\n{"a": 1}\n```') == {"a": 1}


async def test_the_brief_is_understood_through_the_chat_endpoint_with_the_shared_openai_key(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "llm_api_key", "")
    monkeypatch.setattr(s, "tts_api_key", "sk-shared")
    monkeypatch.setattr(s, "llm_model", "")
    seen: list = []
    llm = OpenAIScriptLLM(
        client=fake_client({"company": "Minicor", "announcement": "raised $3.8M", "key_facts": []}, seen)
    )
    facts = await llm.parse_brief("Minicor raised a $3.8M seed round.", None)
    assert facts["company"] == "Minicor"
    path, body = seen[0]
    assert path.endswith("/chat/completions") and body["model"] == "gpt-4o-mini"
    assert body["response_format"] == {"type": "json_object"} and body["messages"][0]["role"] == "system"


async def test_the_story_comes_back_in_the_shape_the_app_expects():
    story = {
        "headline": "Minicor raises $3.8M",
        "dek": "A seed round for desktop automation.",
        "sections": [{"heading": "The news", "paragraphs": ["Minicor raised a seed round."]}],
        "social": {"hook": "Seven rejections, then this.", "post": "Minicor raised $3.8M.", "hashtags": ["#startups"]},
        "segments": [
            {"kind": "intro", "text": "Tonight, Minicor."},
            {"kind": "body", "text": "It raised a seed round."},
        ],
        "ticker_lines": ["MINICOR RAISES SEED"],
        "lower_thirds": [{"title": "Minicor", "subtitle": "Funding round"}],
        "unverified": [],
    }
    llm = OpenAIScriptLLM(client=fake_client(story, []))
    got = await llm.write_story({"company": "Minicor"}, "funding_round", [{"question": "Why?", "answer": "Because."}])
    assert got.headline == "Minicor raises $3.8M" and got.social.hashtags == ["#startups"] and len(got.segments) == 2
