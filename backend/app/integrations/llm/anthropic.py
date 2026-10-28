import json  # noqa: F401  (kept so older imports of this module keep working)

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.integrations.llm.json_llm import SYSTEM, JsonScriptLLM

# The smallest current model: these are short structured-writing jobs, and the bill is the point. Override with LLM_MODEL.
DEFAULT_MODEL = "claude-haiku-5-5"


class AnthropicScriptLLM(JsonScriptLLM):
    def __init__(self) -> None:
        self._client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)

    async def _complete(self, prompt: str) -> str:
        msg = await self._client.messages.create(
            model=get_settings().llm_model or DEFAULT_MODEL,
            max_tokens=8000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")
