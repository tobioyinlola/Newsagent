import re

from app.integrations.llm.base import (
    ScriptDraft,
    ScriptLLM,
    ScriptSegment,
    SocialPost,
    StoryDraft,
    StorySection,
)
from app.services.claims import detect_claims


class MockScriptLLM(ScriptLLM):
    def estimate_cost(self, brief_text: str) -> float:
        return 0.01

    async def parse_brief(self, brief_text: str, website_url: str | None) -> dict:
        sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", brief_text.strip()) if x.strip()]
        first = (sentences[0] if sentences else brief_text).rstrip(".!?")[:200]
        name: list[str] = []
        for w in first.split():  # the opening run of capitalised words is usually the company
            bare = w.rstrip(",;:")
            if bare[:1].isupper() and bare.isalpha():
                name.append(bare)
                if bare != w:  # a comma ends the name
                    break
            elif name:
                break
        sentences = [x.rstrip(".!?") for x in sentences]
        return {
            "company": " ".join(name[:3]) or "Acme",
            "announcement": first,
            "problem": first,
            "usp": first,
            "key_facts": sentences[:5] or [brief_text[:200]],
        }

    async def moderate(self, text: str) -> dict:
        return {"level": "allow", "reasons": []}

    async def write_script(self, facts: dict, tone: str) -> ScriptDraft:
        company = facts.get("company", "this startup")
        segs = [
            ScriptSegment(kind="intro", text=f"Tonight's featured startup: {company}."),
            ScriptSegment(kind="body", text=f"{facts.get('problem', '')} Here is how they solve it."),
            ScriptSegment(kind="outro", text="That was our featured startup. Back to you."),
        ]
        draft = ScriptDraft(
            segments=segs,
            ticker_lines=[f"FEATURED: {company}"],
            lower_thirds=[{"title": company, "subtitle": "Featured startup"}],
            interview_questions=[
                "What problem are you solving, and who feels it most?",
                "What made you start this company?",
                "What has surprised you most since you launched?",
                "Where do you want this to be in a year?",
            ],
        )
        draft.claim_flags = detect_claims(" ".join(s.text for s in segs) + " " + " ".join(facts.get("key_facts", [])))
        return draft

    async def write_story(self, facts: dict, announcement_type: str, answers: list[dict]) -> StoryDraft:
        company = facts.get("company", "this startup")
        kind = announcement_type.replace("_", " ")
        said = [a["answer"].strip() for a in answers if a.get("answer", "").strip()]
        first = said[0] if said else str(facts.get("announcement", ""))
        return StoryDraft(
            headline=f"{company}: {facts.get('announcement', kind)}"[:110],
            dek=f"{company} shares its {kind} with Cover Founder.",
            sections=[
                StorySection(heading="The announcement", paragraphs=[str(facts.get("announcement", "")), first]),
                StorySection(heading="The problem", paragraphs=[str(facts.get("problem", ""))]),
                StorySection(
                    heading="What the company hasn't said",
                    paragraphs=["Revenue, customer numbers and valuation were not disclosed."],
                ),
            ],
            social=SocialPost(
                hook=f"{company} just made a move.",
                post=f"{company}: {facts.get('announcement', kind)}. Watch the full story on Cover Founder.",
                hashtags=["#startups", "#CoverFounder"],
            ),
            segments=[
                ScriptSegment(kind="intro", text=f"Tonight's featured startup: {company}."),
                ScriptSegment(kind="body", text=f"{facts.get('announcement', '')} Let's hear from the founder."),
            ],
            ticker_lines=[f"FEATURED: {company}"],
            lower_thirds=[{"title": company, "subtitle": kind.title()}],
            unverified=[],
            outro=(
                f"That's our look at {company} tonight. Thank you to the founder for joining us and for being so open about "
                "what they are building. If you'd like to know more, search for the company by name and see it for yourself. "
                "For Cover Founder News, thank you for watching."
            ),
        )
