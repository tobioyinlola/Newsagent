"""The scene plan: one validated, persisted description of a video that the producer, the API and the Remotion
compositions all agree on. It stores asset KEYS (never signed URLs), so a video can be rebuilt from it later."""

import hashlib
import json
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.integrations.errors import ProviderError
from app.integrations.storage.base import StorageProvider

SceneType = Literal[
    "presenter_clip",  # real presenter footage from the operator's library (opening shot, cutaway, sign-off)
    "anchor_intro",  # the AI presenter opens the bulletin
    "anchor_explanation",
    "anchor_analysis",
    "anchor_question",  # the AI presenter asks one interview question
    "product_broll",
    "founder_picture_in_picture",
    "founder_split",
    "founder_column",  # the founder, with the question and their words in a column beside them
    "founder_fullscreen",
    "news_closing",  # the AI presenter closes the bulletin
]
# What the Remotion compositions can draw today. A plan using anything else is refused, not silently approximated.
RENDERABLE: set[str] = set(SceneType.__args__) - {"product_broll"}  # type: ignore[attr-defined]
ANCHOR_TYPES = {"anchor_intro", "anchor_explanation", "anchor_analysis", "news_closing"}
FOUNDER_LAYOUT = {
    "founder_picture_in_picture": "pip",
    "founder_split": "split",
    "founder_column": "column",
    "founder_fullscreen": "full",
}
LAYOUT_SCENE = {v: k for k, v in FOUNDER_LAYOUT.items()}
# Where each statement in a scene comes from, so unverified claims are never presented as established fact
Provenance = Literal["owner_script", "founder_statement", "editorial", "presenter_footage"]


class AssetRef(BaseModel):
    kind: Literal["anchor", "question_clip", "take_video", "take_audio", "presenter_clip", "snapshot", "photo"]
    key: str = Field(min_length=1, max_length=500)


class Cue(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str


class Founder(BaseModel):
    name: str = ""
    title: str = ""


class Scene(BaseModel):
    id: str
    order: int = Field(ge=0)
    type: SceneType
    duration_s: float = Field(gt=0, le=1800)
    narration: str | None = None
    headline: str | None = None
    provenance: Provenance = "owner_script"
    asset: AssetRef | None = None  # the main picture/sound for the scene
    question_asset: AssetRef | None = None  # founder scenes: the anchor's question clip (shown as the listening anchor)
    poster: AssetRef | None = None
    question_index: int | None = None
    question: str | None = None
    question_number: int | None = None
    total_questions: int | None = None
    founder: Founder | None = None
    trim_start_s: float = Field(default=0, ge=0)
    cues: list[Cue] = []
    transition: Literal["cut", "fade"] = "cut"
    captions: bool = True
    requirements: list[str] = []  # what must be true to render it (assets exist, durations match, ...)

    @model_validator(mode="after")
    def _needs(self) -> "Scene":
        if self.type != "product_broll" and self.asset is None:
            raise ValueError(f"scene {self.id} ({self.type}) needs a media asset")
        if self.type in FOUNDER_LAYOUT and (self.question_asset is None or self.founder is None):
            raise ValueError(f"scene {self.id} ({self.type}) needs the question clip and the founder's name")
        return self


class Caption(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str


class ScenePlan(BaseModel):
    version: int = 1
    project_id: str
    script_version_id: str | None = None
    aspect: Literal["16:9"] = "16:9"
    layout: str = "pip"
    scenes: list[Scene]
    captions: list[Caption] = []
    total_s: float = Field(gt=0)
    # statements that look like factual claims and have not been confirmed by the owner. Reported, never invented.
    unconfirmed_claims: list[str] = []

    @model_validator(mode="after")
    def _consistent(self) -> "ScenePlan":
        if [s.order for s in self.scenes] != list(range(len(self.scenes))):
            raise ValueError("scene order must run 0, 1, 2, ... without gaps")
        if len({s.id for s in self.scenes}) != len(self.scenes):
            raise ValueError("scene ids must be unique")
        bad = sorted({s.type for s in self.scenes if s.type not in RENDERABLE})
        if bad:
            raise ValueError(f"the renderer cannot draw these scenes yet: {', '.join(bad)}")
        if abs(sum(s.duration_s for s in self.scenes) - self.total_s) > 0.05:
            raise ValueError("total_s must equal the sum of the scene durations")
        return self

    def hash(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


class ScenePlanError(ProviderError):
    """The plan cannot be rendered (missing media, ...). Fails fast with a message the owner can act on."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems), "invalid_input")
        self.problems = problems
        self.user_message = "Some media for this video is missing or unusable: " + "; ".join(problems[:3])


def asset_refs(plan: ScenePlan) -> list[tuple[Scene, AssetRef]]:
    out: list[tuple[Scene, AssetRef]] = []
    for s in plan.scenes:
        for ref in (s.asset, s.question_asset, s.poster):
            if ref is not None:
                out.append((s, ref))
    return out


async def validate_assets(plan: ScenePlan, storage: StorageProvider) -> None:
    """Every referenced file must exist and not be empty, BEFORE any render time is spent."""
    problems: list[str] = []
    seen: dict[str, int | None] = {}
    for scene, ref in asset_refs(plan):
        if ref.key not in seen:
            try:
                seen[ref.key] = await storage.size(ref.key)
            except Exception:  # noqa: BLE001
                seen[ref.key] = None
        if not seen[ref.key]:
            if ref.kind == "snapshot":
                continue  # a still is decoration: the video does not depend on it
            problems.append(
                f"scene {scene.order + 1} ({scene.type.replace('_', ' ')}): {ref.kind.replace('_', ' ')} is missing"
            )
    if problems:
        raise ScenePlanError(problems)


def to_render_scenes(plan: ScenePlan, url: Callable[[str], str]) -> list[dict]:
    """The renderer's scene list, with short-lived signed URLs minted now."""
    out: list[dict] = []
    for s in plan.scenes:
        if s.type == "presenter_clip":
            assert s.asset
            out.append({"type": "clip", "src": url(s.asset.key), "seconds": s.duration_s})
        elif s.type == "anchor_question":
            assert s.asset
            out.append({"type": "question", "src": url(s.asset.key), "seconds": s.duration_s})
        elif s.type in ANCHOR_TYPES:
            assert s.asset
            out.append({"type": "anchor", "src": url(s.asset.key), "seconds": s.duration_s})
        else:
            assert s.asset and s.question_asset and s.founder
            scene: dict = {
                "type": "answer",
                "seconds": s.duration_s,
                "startFromSeconds": s.trim_start_s,
                "pipSrc": url(s.question_asset.key),
                "founder": s.founder.model_dump(),
                "src": None,
                "question": s.question,
                "questionNumber": s.question_number,
                "totalQuestions": s.total_questions,
                "cues": [c.model_dump() for c in s.cues],
                "layout": FOUNDER_LAYOUT[s.type],
            }
            if s.asset.kind == "take_video":
                scene["src"] = url(s.asset.key)
            else:
                scene["audioSrc"] = url(s.asset.key)
            if s.poster:
                if s.poster.kind == "photo":
                    scene["photoSrc"] = url(s.poster.key)
                else:
                    scene["posterSrc"] = url(s.poster.key)
            out.append(scene)
    return out
