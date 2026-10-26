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
        announcement = (facts.get("announcement") or "").strip().rstrip(".")
        problem = (facts.get("problem") or announcement or "a problem many people know well").strip().rstrip(".")
        usp = (facts.get("usp") or "").strip().rstrip(".")
        details = [str(f).strip().rstrip(".") for f in (facts.get("key_facts") or []) if str(f).strip()][:4]
        detail_text = " ".join(f"{d}." for d in details) or f"{company} is only getting started."
        lead = f"{announcement}. " if announcement else ""
        segs = [
            ScriptSegment(
                kind="intro",
                text=(
                    f"Good evening, and welcome to tonight's featured startup. Tonight we are looking at {company}, "
                    f"a young company with news to share. {lead}"
                    "It is the kind of story that shows where a new idea can go when it meets a real need, "
                    "and we have the founder here to talk about it."
                ),
            ),
            ScriptSegment(
                kind="body",
                text=(
                    f"Let us start with the problem. {problem}. For the people who live with it every day, that is "
                    "not a small inconvenience, it is a daily cost in time, money and opportunity.\n\n"
                    f"{company} set out to change that. {usp + '. ' if usp else ''}"
                    "The team has built something practical that people can start using straight away, "
                    "rather than a promise of what might come later.\n\n"
                    f"Here is what we know. {detail_text} "
                    "That is the foundation, and the next stage is putting it in front of more people and learning "
                    "from how they use it."
                ),
            ),
            ScriptSegment(
                kind="explanation",
                text=(
                    f"Before we hear from the founder, here is a plain summary of what {company} does. {lead}"
                    f"The company is aimed at the people who live with this problem every day: {problem}. "
                    "What sets it apart is that it starts from their everyday reality instead of asking them "
                    "to change how they work. Keep that in mind as you listen, because it shapes every answer "
                    "you are about to hear."
                ),
            ),
            ScriptSegment(
                kind="outro",
                text=(
                    f"That was {company}, tonight's featured startup. We have heard the idea, the problem it "
                    "addresses and, in the founder's own words, why it matters. Keep an eye on this company as it "
                    "grows and shares more of what it learns along the way. For now, it is back to the studio."
                ),
            ),
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
