from abc import ABC, abstractmethod

from pydantic import BaseModel


class ScriptSegment(BaseModel):
    kind: str  # intro | body | question_lead | outro
    text: str


class ClaimFlag(BaseModel):
    text: str
    category: str  # revenue | users | funding | ranking | superlative
    confirmed: bool = False


class ScriptDraft(BaseModel):
    segments: list[ScriptSegment]
    ticker_lines: list[str]
    lower_thirds: list[dict]
    interview_questions: list[str]
    claim_flags: list[ClaimFlag] = []


class StorySection(BaseModel):
    heading: str
    paragraphs: list[str]


class SocialPost(BaseModel):
    hook: str  # the line that stops the scroll
    post: str
    hashtags: list[str] = []


class StoryDraft(BaseModel):
    """What is written after the interview: the news story, the social post, and the short script the presenter speaks."""

    headline: str
    dek: str
    sections: list[StorySection]
    social: SocialPost
    segments: list[ScriptSegment]  # intro + body only; the standard sign-off is added by the caller
    ticker_lines: list[str]
    lower_thirds: list[dict]
    unverified: list[str] = []  # things the founder said that we could not check; the story hedges them


class ScriptLLM(ABC):
    @abstractmethod
    def estimate_cost(self, brief_text: str) -> float: ...

    @abstractmethod
    async def parse_brief(self, brief_text: str, website_url: str | None) -> dict: ...

    @abstractmethod
    async def moderate(self, text: str) -> dict:
        """Return {"level": "allow"|"review"|"block", "reasons": [str]} for content we are about to publish."""

    @abstractmethod
    async def write_script(self, facts: dict, tone: str) -> ScriptDraft: ...

    @abstractmethod
    async def write_story(self, facts: dict, announcement_type: str, answers: list[dict]) -> StoryDraft:
        """One call after the interview. `answers` is [{question, answer}] (what the founder actually said)."""
