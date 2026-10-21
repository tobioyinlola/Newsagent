from app.integrations.llm.base import ScriptDraft, ScriptLLM, ScriptSegment
from app.services.claims import detect_claims


class MockScriptLLM(ScriptLLM):
    def estimate_cost(self, brief_text: str) -> float:
        return 0.01

    async def parse_brief(self, brief_text: str, website_url: str | None) -> dict:
        first = brief_text.strip().split(".")[0][:120]
        return {"company": "Acme", "problem": first, "usp": first, "key_facts": [brief_text[:200]]}

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
            interview_questions=["What problem are you solving?", "Why now?"],
        )
        draft.claim_flags = detect_claims(" ".join(s.text for s in segs) + " " + " ".join(facts.get("key_facts", [])))
        return draft
