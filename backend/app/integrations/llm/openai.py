"""The writing jobs through any OpenAI-compatible `/chat/completions` endpoint (OpenAI by default).

Uses the same key as the interviewer's voice unless LLM_API_KEY is set, so one OpenAI account can run the whole product."""

import httpx

from app.config import get_settings
from app.integrations.llm.json_llm import SYSTEM, JsonScriptLLM

# A small, inexpensive model: these are short structured-writing jobs. Override with LLM_MODEL.
DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIScriptLLM(JsonScriptLLM):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        key = s.llm_api_key or s.tts_api_key or s.transcription_api_key
        self._client = client or httpx.AsyncClient(
            base_url=s.llm_api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {key}"},
            timeout=60,
        )

    async def _complete(self, prompt: str) -> str:
        r = await self._client.post(
            "/chat/completions",
            json={
                "model": get_settings().llm_model or DEFAULT_MODEL,
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""
