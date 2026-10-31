from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    about: str = ""  # the "About <company>" boilerplate paragraph of the press release
    unverified: list[str] = []  # things the founder said that we could not check; the story hedges them
    chyrons: list[str] = []  # one per answer, in order: the headline bar shown while the founder speaks
    answer_bridges: list[str] = []
    startup_summary: str = ""
    outro: str = ""  # the presenter's closing words (a natural wrap-up that points viewers to the product's website)

    @field_validator("unverified", "chyrons", "ticker_lines", "answer_bridges", mode="before")
    @classmethod
    def _as_text_list(cls, v):
        """Language models sometimes answer one item as a plain string, or a list as {key: text}. Accept both shapes."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, dict):
            v = list(v.values())
        return [str(x) for x in v if str(x).strip()] if isinstance(v, list) else v

    @field_validator("about", mode="before")
    @classmethod
    def _about_text(cls, v):
        return " ".join(str(x) for x in v) if isinstance(v, list) else (v or "")

    @field_validator("outro", "startup_summary", mode="before")
    @classmethod
    def _as_text(cls, v):
        if isinstance(v, list):
            return " ".join(str(x) for x in v)
        return v or ""

    @field_validator("lower_thirds", mode="before")
    @classmethod
    def _as_dict_list(cls, v):
        if isinstance(v, dict):
            return [v]
        return v or []


class NewsScene(BaseModel):
    narration: str = Field(min_length=1, max_length=3000)
    image_hint: str = Field(default="", max_length=1000)
    motion: Literal["slow_zoom_in", "slow_zoom_out", "pan_left", "pan_right", "static"] = "slow_zoom_in"
    duration_s: int = Field(default=8, ge=3, le=60)
    image_id: str | None = None


class NewsDraft(BaseModel):
    headline: str = Field(min_length=5, max_length=180)
    summary: str = Field(min_length=10, max_length=500)
    body: str = Field(min_length=40, max_length=20000)
    presenter_script: str = Field(min_length=20, max_length=15000)
    scenes: list[NewsScene] = Field(default_factory=list, max_length=20)


class ScriptLLM(ABC):
    async def write_news(self, source_text: str, source_name: str) -> NewsDraft:
        raise NotImplementedError("News rewriting is not configured for this provider")

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
