from app.integrations.llm.base import ScriptDraft, ScriptLLM, ScriptSegment
from app.services.claims import detect_claims


class MockScriptLLM(ScriptLLM):
    def estimate_cost(self, brief_text: str) -> float:
        return 0.01

    async def parse_brief(self, brief_text: str, website_url: str | None) -> dict:
        first = brief_text.strip().split(".")[0][:120]
        words = first.split()
        name: list[str] = []
        for w in words:  # the opening run of capitalised words is usually the company
            if w[:1].isupper() and w.isalpha():
                name.append(w)
            elif name:
                break
        sentences = [x.strip() for x in brief_text.replace("\n", " ").split(".") if x.strip()]
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
            ScriptSegment(
                kind="explanation",
                text=f"Before we hear from the founder, here is what {company} does and who it is for.",
            ),
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
