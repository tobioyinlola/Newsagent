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

    async def analyze_outreach_reply(self, context: dict) -> dict:
        """A deterministic stand-in for the model, used in development and tests: it reads obvious cues in the reply."""
        text = str(context.get("latest", ""))
        low = text.lower()
        out: dict = {"intent": "unclear", "confidence": 0.9, "summary": text[:120], "quoted_price": None, "currency": None, "deadline": None, "asks": [], "account_details": None, "suspicious": False}
        if not text.strip():
            return {**out, "confidence": 0.1}
        if re.search(r"ignore (all |your )?(previous|prior) instructions|system prompt", low):
            out["suspicious"] = True
        acct = re.search(r"account (number|no\.?)\D{0,6}(\d{6,})", low)
        iban = re.search(r"\b([a-z]{2}\d{2}[a-z0-9]{10,30})\b", low)
        if acct or iban:
            out.update(intent="sends_account_details", account_details={"account_number": acct.group(2) if acct else None, "iban": iban.group(1).upper() if iban else None, "bank_name": (re.search(r"bank[:\s]+([A-Za-z ]{3,30})", text) or [None, None])[1]})
        elif re.search(r"(not interested|no thanks|cannot publish|can't publish|decline)", low):
            out["intent"] = "declines"
        elif re.search(r"(complain|legal|lawyer|sue\b|scam|spam)", low):
            out["intent"] = "complaint"
        elif m := re.search(r"([$€£₦]|usd|ngn|eur|gbp)\s?([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s?(usd|ngn|dollars|naira)", low):
            amount = (m.group(2) or m.group(3) or "0").replace(",", "")
            out.update(intent="quotes_price", quoted_price=float(amount), currency=(m.group(1) or m.group(4) or "").upper()[:3] or None)
        elif re.search(r"how (will|do) you pay|payment (terms|method)|pay us", low):
            out["intent"] = "requests_payment_terms"
        elif "?" in text:
            out.update(intent="asks_question", asks=[text.strip()[:100]])
        elif re.search(r"(yes|sure|happy to|can do|we can)", low):
            out["intent"] = "accepts"
        return out

    async def draft_outreach_reply(self, context: dict, analysis: dict) -> dict:
        who = context.get("contact_name") or "there"
        sign = context.get("sender_name") or "The Cover Founder team"
        intent = analysis.get("intent")
        step, body = "other", "Thank you for your message. Could you tell us more about how we can proceed?"
        if intent == "quotes_price":
            step, body = "discuss_price", "Thank you for sharing your rate. I will confirm it with the team and come back to you shortly."
        elif intent == "sends_account_details":
            step, body = "confirm_account_details", "Thank you for sending your details. We will review them and confirm shortly."
        elif intent == "accepts":
            step, body = "ask_rates", "Thank you, that is great news. Could you share your rate for a sponsored article and your usual turnaround time?"
        elif intent == "asks_question":
            step, body = "answer_question", "Thanks for your question. I will check and come back to you shortly."
        elif intent == "requests_payment_terms":
            step, body = "payment_terms", "Thank you. I will check the payment arrangements with the team and come back to you."
        return {"subject": "", "body": f"Hello {who},\n\n{body}\n\nKind regards,\n{sign}", "step": step}

    async def draft_marketing_copy(self, brief: str, category: str, tags: list[str]) -> dict:
        topic = " ".join(brief.split())[:200].rstrip(".")
        return {
            "subject": topic[:58] or "News from Cover Founder",
            "preheader": "A quick note from Cover Founder.",
            "body": f"Hi {{{{first_name|there}}}},\n\n{topic}.\n\n{{{{company}}}} is set up and ready when you are.",
        }

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
                StorySection(
                    heading="",
                    paragraphs=[
                        p
                        for p in (
                            str(facts.get("announcement", "")),
                            first,
                            str(facts.get("problem", "")),
                            "Revenue, customer numbers and valuation were not disclosed.",
                        )
                        if p
                    ],
                )
            ],
            about=f"{company} is a company that shares its {kind} with Cover Founder.",
            closing_line=f"{company} is building for the people it serves, one {kind} at a time.",
            social=SocialPost(
                hook=f"{company} just made a move.",
                post=f"{company}: {facts.get('announcement', kind)}. Watch the full story on Cover Founder.",
                hashtags=["#startups", "#CoverFounder"],
            ),
            segments=[
                ScriptSegment(kind="intro", text=f"Tonight's featured startup: {company}."),
                ScriptSegment(
                    kind="body",
                    text=f"{facts.get('announcement', '')} Joining us in the studio is {facts.get('founder_name') or 'the founder'}.",
                ),
            ],
            ticker_lines=[f"FEATURED: {company}"],
            lower_thirds=[{"title": company, "subtitle": kind.title()}],
            unverified=[],
            chyrons=[
                f"{str(facts.get('founder_name') or 'Founder').split()[-1].upper()}: {a['answer'].strip()[:40].upper()}"
                for a in answers
            ],
            outro=(
                f"That's our look at {company} tonight. Thank you to the founder for joining us and for being so open about "
                "what they are building. If you'd like to know more, search for the company by name and see it for yourself. "
                "For Cover Founder News, thank you for watching."
            ),
        )

    async def write_news(self, source_text: str, source_name: str):
        from app.integrations.llm.base import NewsDraft, NewsScene

        # Deterministic demo copy within the standalone editorial word limits.
        source_words = source_text.split()
        body_words = (f"According to {source_name}, " + source_text + " Cover Founder News is following this technology development.").split()
        body = " ".join((body_words * (220 // len(body_words) + 1))[:220])
        script_words = (f"According to {source_name}, " + " ".join(source_words[:45]) + " Cover Founder News is following this developing technology story. Details are attributed to the original source. Further updates will be reported as information becomes available.").split()
        script = " ".join((script_words * 3)[:80])
        return NewsDraft(
            headline="Technology update: a new chapter for business",
            summary=f"Cover Founder News reviews the latest technology development reported by {source_name}.",
            body=body,
            presenter_script=script,
            scenes=[
                NewsScene(
                    narration=script, image_hint="An editorial image illustrating the announcement", duration_s=20
                )
            ],
        )
