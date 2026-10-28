"""The writing jobs (understand the brief, moderate, write the interview questions and the story), independent of which
language-model vendor answers. A vendor adapter only has to implement `_complete`: prompt in, text out."""

import json
from abc import abstractmethod

from app.integrations.llm.base import ScriptDraft, ScriptLLM, StoryDraft
from app.services.claims import detect_claims

SYSTEM = (
    "You write scripts for a short news-style video on the Cover Founder channel, which features a startup. "
    "Voice: expert, authoritative, inspiring, serious but approachable, active not passive. Never reference "
    "any other real news network. Never invent facts: use only "
    "the supplied facts. Reply with JSON only."
)


def parse_json_object(text: str) -> dict:
    """The JSON object in a model's reply, even if it wrapped it in prose or a code fence."""
    return json.loads(text[text.index("{") : text.rindex("}") + 1])


class JsonScriptLLM(ScriptLLM):
    @abstractmethod
    async def _complete(self, prompt: str) -> str:
        """Send SYSTEM + prompt to the vendor's model and return its text reply."""

    def estimate_cost(self, brief_text: str) -> float:
        return 0.05

    async def _json(self, prompt: str) -> dict:
        return parse_json_object(await self._complete(prompt))

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
            "Write a 60-90 second anchor script as JSON with keys segments [{kind,text}], "
            "ticker_lines [str], lower_thirds [{title,subtitle}], interview_questions [str]. "
            "interview_questions: exactly 4 short, open questions (each under 25 words, never yes/no) that a "
            "presenter would ask the founder about THIS announcement, each answerable in about 40 seconds, "
            "ordered from the story to the vision; address the founder directly, do not name them in the questions. "
            f"Tone: {tone}. Facts: {json.dumps(facts)}"
        )
        draft = ScriptDraft.model_validate(raw)
        text = " ".join(s.text for s in draft.segments)
        draft.claim_flags = detect_claims(text)  # deterministic check, not left to the LLM
        return draft

    async def write_story(self, facts: dict, announcement_type: str, answers: list[dict]) -> StoryDraft:
        said = "\n".join(f"Q: {a['question']}\nA: {a['answer']}" for a in answers)[:8000]
        raw = await self._json(
            "Write the Cover Founder news feature for this announcement, as JSON with keys: headline (under 100 chars), "
            "dek (one sentence, under 220 chars), sections [{heading, paragraphs [str]}] (a thorough, detailed feature of 6 to 8 "
            "sections, each with 2 to 4 full paragraphs, about 700 to 900 words in all: the news itself and when it happens; the "
            "problem and who feels it; how the product works in concrete terms; the founders and why they are the ones to build it; "
            "what customers or users get; what the founder said in the interview, quoted where it is strong; why it matters for the "
            'market; what comes next; and a last section titled "What the company hasn\'t said" listing what was NOT disclosed, such '
            "as revenue, customers or valuation, when it was not), social {hook (under 90 chars, makes people stop scrolling), "
            'post (under 270 chars, plain, no hype), hashtags (at most 4)}, segments [{kind: "intro"|"body", text}] (what the '
            "presenter says aloud before the interview: 70 to 90 words in total, in the warm, confident voice of a TV news presenter, "
            "setting up the story and handing over to the founder), outro (what the presenter says aloud to close the programme: 100 "
            "to 140 words, natural and conversational like a TV presenter signing off: recap what was announced and why it matters, "
            "thank the founder by name, and invite viewers to look the product up. If a website is given in the facts, say the address "
            "aloud the way a presenter would, such as 'acme dot com'; if not, say to search for the company by name. Never read out a "
            "full URL with slashes. Before the final sign-off, always invite viewers who want their business or founder story featured on Cover Founder to get in touch. End with a sign-off for Cover Founder News), chyrons [str] (exactly one per interview answer below, in the same order: a news-channel headline bar for while that answer plays, in the form 'SURNAME: WHAT THEY SAID IN A FEW WORDS', under 60 characters, drawn only from that answer), ticker_lines (2 or 3 short strings), lower_thirds "
            "[{title, subtitle}] (one, short), unverified [str] (claims the founder made that the facts do not support; the story must "
            "hedge them with 'says' or 'the company reports'). Use only the facts and the founder's own words below; never invent "
            "numbers, names or quotes. "
            f"Announcement type: {announcement_type}. Facts: {json.dumps(facts)}\nInterview:\n{said}"
        )
        return StoryDraft.model_validate(raw)
