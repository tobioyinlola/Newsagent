"""Pipeline steps. Each is idempotent (see runner.run_step) and every paid call goes through SpendGuard."""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.integrations.avatar.base import AvatarRequest
from app.integrations.renderer.base import RenderRequest
from app.models import Asset, BrandKit, Job, Project, ScriptVersion
from app.services import state_machine as sm
from app.services.spend_guard import LimitReached, SpendGuard

FORMATS = [
    {"format": "16x9", "width": 1920, "height": 1080},
    {"format": "9x16", "width": 1080, "height": 1920},
]

# Locked channel identity and mandatory disclosures (hard rules 1 and 2). Never user-editable.
CHANNEL_IDENTITY = {"name": "Startup Spotlight Network", "locked": True}
DISCLOSURES = {"tag": "Featured", "anchor": "AI-generated anchor"}
BANNED_TERMS = ["cnn", "bbc", "fox news", "sky news", "al jazeera", "msnbc", "reuters", "bloomberg tv"]


def input_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class StepOutcome:
    result: dict
    cost: Decimal = Decimal("0")


async def approved_script(session: AsyncSession, project_id: str) -> ScriptVersion:
    script = (
        (
            await session.execute(
                select(ScriptVersion)
                .where(ScriptVersion.project_id == project_id, ScriptVersion.approved.is_(True))
                .order_by(ScriptVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )
    if script is None:
        raise RuntimeError("no approved script for project")
    return script


def anchor_text(script: ScriptVersion) -> str:
    return " ".join(s["text"] for s in script.segments)


async def anchor_inputs(session: AsyncSession, project: Project) -> dict:
    script = await approved_script(session, project.id)
    return {
        "script_id": script.id,
        "text": anchor_text(script),
        "accent": project.voice_accent,
        "anchor": project.anchor_id,
        "accent_override": project.accent_override,
    }


async def build_overlay_props(session: AsyncSession, project: Project, script: ScriptVersion) -> dict:
    kit = (
        (
            await session.execute(
                select(BrandKit).where(BrandKit.workspace_id == project.workspace_id).order_by(BrandKit.version.desc())
            )
        )
        .scalars()
        .first()
    )
    return {
        "channel": CHANNEL_IDENTITY,
        "disclosures": DISCLOSURES,
        "brand": {
            "primary": kit.primary_color if kit else "#0B3D91",
            "accent": project.accent_override or (kit.accent_color if kit else "#F5A623"),
        },
        "tickerLines": script.ticker_lines,
        "lowerThirds": script.lower_thirds,
    }


async def anchor_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    script = await approved_script(session, project.id)
    avatar = registry.get_avatar()
    req = AvatarRequest(
        script_text=anchor_text(script),
        voice_accent=project.voice_accent,
        avatar_id=project.anchor_id,
        transparent=True,
    )
    res = await guard.reserve(project.workspace_id, avatar.name, avatar.estimate_cost(req))
    try:
        out = await avatar.generate(req)
    except Exception:
        await guard.release(res)
        raise
    cost = await guard.settle(res, out.cost)
    key = f"projects/{project.id}/anchor.webm"
    session.add(Asset(project_id=project.id, type="anchor", storage_key=key, duration=Decimal(str(out.duration_s))))
    return StepOutcome({"video_url": out.video_url, "duration_s": out.duration_s, "key": key}, cost)


async def final_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    script = await approved_script(session, project.id)
    renderer = registry.get_renderer()
    anchor = (
        (await session.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "anchor")))
        .scalars()
        .first()
    )
    props = await build_overlay_props(session, project, script)
    assert anchor is not None, "anchor asset must exist before final render"
    req = RenderRequest(
        composition="NewsStudio",
        props=props,
        outputs=FORMATS,
        input_urls={"anchor": registry.get_storage().presign_get(anchor.storage_key)},
        output_prefix=f"projects/{project.id}/final",
    )
    res = await guard.reserve(project.workspace_id, "renderer", renderer.estimate_cost(req))
    try:
        render_id = await renderer.submit(req)
        status = await _wait(renderer, render_id)
    except Exception:
        await guard.release(res)
        raise
    cost = await guard.settle(res, renderer.estimate_cost(req))
    for fmt, key in zip(FORMATS, status.output_keys, strict=False):
        session.add(Asset(project_id=project.id, type="render", storage_key=key, format=fmt["format"]))
    return StepOutcome({"props": props, "output_keys": status.output_keys}, cost)


async def _wait(renderer, render_id: str):
    import asyncio

    while True:
        st = await renderer.status(render_id)
        if st.status == "succeeded":
            return st
        if st.status == "failed":
            raise RuntimeError(st.error or "render failed")
        await asyncio.sleep(2)


def quality_gate(result: dict, outputs: int) -> list[str]:
    """Stage 11 (subset): disclosure + banned-content checks. Loudness/lip-sync arrive in Phase 1."""
    problems = []
    props = result["props"]
    if props["disclosures"] != DISCLOSURES:
        problems.append("missing mandatory disclosure labels")
    blob = json.dumps([props["tickerLines"], props["lowerThirds"]]).lower()
    for term in BANNED_TERMS:
        if term in blob:
            problems.append(f"banned network name in overlays: {term}")
    if len(result["output_keys"]) < outputs:
        problems.append("missing output formats")
    return problems


__all__ = ["Job", "LimitReached", "sm"]
