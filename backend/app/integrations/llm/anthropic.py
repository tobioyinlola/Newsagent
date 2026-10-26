import json

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.integrations.llm.base import ScriptDraft, ScriptLLM
from app.services.claims import detect_claims

MODEL = "claude-sonnet-5-5"

SYSTEM = (
    "You write scripts for a short news-style video on the Cover Founder channel, which features a startup. "
    "Voice: expert, authoritative, inspiring, serious but approachable, active not passive. Never reference "
    "any other real news network. Never invent facts: use only "
    "the supplied facts. Reply with JSON only."
)


class AnthropicScriptLLM(ScriptLLM):
    def __init__(self) -> None:
        self._client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)

    def estimate_cost(self, brief_text: str) -> float:
        return 0.05

    async def _json(self, prompt: str) -> dict:
        msg = await self._client.messages.create(
            model=MODEL,
            max_tokens=6000,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        return json.loads(text[text.index("{") : text.rindex("}") + 1])

    async def parse_brief(self, brief_text: str, website_url: str | None) -> dict:
        return await self._json(
            "The text below is a startup's announcement, news script or brief. Work out what they are announcing. "
            "Extract JSON with keys company (the startup's name), announcement (one sentence: what is being "
            "announced), problem, usp, key_facts (list of short concrete facts, at most 8), region, tone from "
            f"this text:\n{brief_text}\nWebsite: {website_url or 'n/a'}"
        )

    async def moderate(self, text: str) -> dict:
        raw = await self._json(
            "You are a content-safety reviewer for short promotional videos about startups. Decide whether this "
            'text may be published. Reply with JSON {"level": "allow"|"review"|"block", "reasons": [short '
            "category names]}. block = clearly illegal, violent, hateful, sexual or fraudulent. review = misleading "
            "health/financial claims, false endorsements, politics, or anything you are unsure about. Otherwise allow.\n\n"
            + text[:6000]
        )
        level = (
            raw.get("level") if raw.get("level") in {"allow", "review", "block"} else "review"
        )  # unclear -> a human looks
        return {"level": level, "reasons": [str(r)[:60] for r in raw.get("reasons", [])][:5]}

    async def write_script(self, facts: dict, tone: str) -> ScriptDraft:
        raw = await self._json(
            "Write the anchor script for a news-style feature on this startup as JSON with keys "
            "segments [{kind,text}], ticker_lines [str], lower_thirds [{title,subtitle}], interview_questions [str]. "
            "The script is spoken aloud by a presenter, so write full, flowing, detailed paragraphs, never one-liners. "
            "segments, in this order, with these lengths: "
            "intro (60-80 words: hook the viewer, name the startup, say what is being announced and why it matters now); "
            "body (180-240 words in two or three short paragraphs: the problem and who feels it, what the startup "
            "built and how it works, the concrete facts supplied, and what happens next); "
            "explanation (90-120 words, spoken before the founder interview: plainly explain what the startup does, "
            "who it is for and what makes it different, so a newcomer understands the interview that follows); "
            "outro (50-70 words: sum up the story, say what to watch for next, and hand back to the studio). "
            "Use only the supplied facts; where a fact is missing, describe the idea in general terms and never invent "
            "numbers, customers, funding or dates. "
            "interview_questions: exactly 4 short, open questions (each under 25 words, never yes/no) that a "
            "presenter would ask the founder about THIS announcement, each answerable in about 40 seconds, "
            "ordered from the story to the vision; address the founder directly, do not name them in the questions. "
            f"Tone: {tone}. Facts: {json.dumps(facts)}"
        )
        draft = ScriptDraft.model_validate(raw)
        text = " ".join(s.text for s in draft.segments)
        draft.claim_flags = detect_claims(text)  # deterministic check, not left to the LLM
        return draft
