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
