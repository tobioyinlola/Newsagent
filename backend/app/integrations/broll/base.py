from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BrollResult:
    data: bytes
    content_type: str
    duration_s: float
    cost: float  # what the vendor charged, in USD


class BrollProvider(ABC):
    """Makes a short silent clip from a text prompt. Its output is SYNTHETIC: the pipeline marks it as such in the plan
    and on screen, and never presents it as real footage of a company, product, event or person."""

    name: str

    @abstractmethod
    def estimate_cost(self, prompt: str, seconds: float) -> float: ...

    @abstractmethod
    async def generate(self, prompt: str, seconds: float) -> BrollResult: ...
