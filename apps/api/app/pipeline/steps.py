"""Pipeline steps. Each is idempotent (see runner.run_step) and every paid call goes through SpendGuard."""

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.integrations.avatar.base import AvatarRequest
from app.integrations.renderer.base import RenderRequest
from app.models import Asset, BrandKit, Job, Project, ScriptVersion
from app.services import state_machine as sm
from app.services.captions import build_srt
from app.services.safety import find_banned
from app.services.spend_guard import LimitReached, SpendGuard

FORMATS = [
    {"kind": "video", "format": "16x9", "width": 1920, "height": 1080},
    {"kind": "video", "format": "9x16", "width": 1080, "height": 1920},
    {"kind": "thumbnail", "format": "16x9", "name": "thumbnail", "width": 1920, "height": 1080},
]
PREVIEW = [{"kind": "video", "format": "16x9", "name": "preview", "width": 1920, "height": 1080, "scale": 0.5}]

# Locked channel identity and mandatory disclosures (hard rules 1 and 2). Never user-editable.
CHANNEL_IDENTITY = {"name": "Startup Spotlight Network", "locked": True}
DISCLOSURES = {"tag": "Featured", "anchor": "AI-generated anchor"}


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


async def current_kit(session: AsyncSession, workspace_id: str) -> BrandKit | None:
    return (
        (
            await session.execute(
                select(BrandKit).where(BrandKit.workspace_id == workspace_id).order_by(BrandKit.version.desc())
            )
        )
        .scalars()
        .first()
    )


async def anchor_inputs(session: AsyncSession, project: Project) -> dict:
    script = await approved_script(session, project.id)
    kit = await current_kit(session, project.workspace_id)
    return {
        "brand_version": kit.version if kit else 0,
        "glossary": kit.pronunciation_glossary if kit else {},
        "script_id": script.id,
        "text": anchor_text(script),
        "accent": project.voice_accent,
        "anchor": project.anchor_id,
        "accent_override": project.accent_override,
    }


async def build_overlay_props(
    session: AsyncSession, project: Project, script: ScriptVersion, anchor_duration_s: float
) -> dict:
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
        "anchorDurationSeconds": anchor_duration_s,
        "tickerLines": script.ticker_lines,
        "lowerThirds": script.lower_thirds,
    }


async def anchor_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    script = await approved_script(session, project.id)
    avatar = registry.get_avatar()
    kit = await current_kit(session, project.workspace_id)
    req = AvatarRequest(
        script_text=anchor_text(script),
        pronunciation=(kit.pronunciation_glossary if kit else None) or None,
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


async def _render(session: AsyncSession, project: Project, guard: SpendGuard, outputs: list[dict], prefix: str):
    script = await approved_script(session, project.id)
    renderer = registry.get_renderer()
    anchor = (
        (await session.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "anchor")))
        .scalars()
        .first()
    )
    assert anchor is not None, "anchor asset must exist before rendering"
    props = await build_overlay_props(session, project, script, float(anchor.duration or 60))
    req = RenderRequest(
        composition="NewsStudio",
        props=props,
        outputs=outputs,
        input_urls={"anchor": registry.get_storage().presign_get(anchor.storage_key)},
        output_prefix=f"projects/{project.id}/{prefix}",
    )
    res = await guard.reserve(project.workspace_id, "renderer", renderer.estimate_cost(req))
    try:
        render_id = await renderer.submit(req)
        status = await _wait(renderer, render_id)
    except Exception:
        await guard.release(res)
        raise
    cost = await guard.settle(res, renderer.estimate_cost(req))
    return script, anchor, props, status, cost


async def preview_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    _, _, props, status, cost = await _render(session, project, guard, PREVIEW, "preview")
    session.add(Asset(project_id=project.id, type="preview", storage_key=status.output_keys[0], format="16x9"))
    return StepOutcome({"props": props, "output_keys": status.output_keys}, cost)


async def final_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    script, anchor, props, status, cost = await _render(session, project, guard, FORMATS, "final")
    for o, key in zip(FORMATS, status.output_keys, strict=False):
        atype = "thumbnail" if o["kind"] == "thumbnail" else "render"
        session.add(Asset(project_id=project.id, type=atype, storage_key=key, format=o["format"]))
    renderer = registry.get_renderer()
    analyses = {}
    for o, key in zip(FORMATS, status.output_keys, strict=False):
        if o["kind"] == "video":
            a = await renderer.analyze(registry.get_storage().presign_get(key))
            analyses[key] = asdict(a)
    srt = build_srt(script.segments, float(anchor.duration or 60))
    srt_key = f"projects/{project.id}/final/captions.srt"
    await registry.get_storage().put(srt_key, srt.encode(), "application/x-subrip")
    session.add(Asset(project_id=project.id, type="caption", storage_key=srt_key))
    return StepOutcome(
        {"props": props, "output_keys": status.output_keys, "srt_key": srt_key, "analyses": analyses}, cost
    )


async def _wait(renderer, render_id: str):
    import asyncio

    while True:
        st = await renderer.status(render_id)
        if st.status == "succeeded":
            return st
        if st.status == "failed":
            raise RuntimeError(st.error or "render failed")
        await asyncio.sleep(2)


def quality_gate(result: dict, outputs: int) -> list[str]:  # outputs = expected number of rendered files
    """Stage 11: disclosures, banned names, and measured video/audio properties of each rendered video.

    Loudness is normalised by the renderer and only recorded here; clipping, silence, wrong length and
    audio/video drift fail the video before the owner sees it.
    """
    problems = []
    props = result["props"]
    if props["disclosures"] != DISCLOSURES:
        problems.append("missing mandatory disclosure labels")
    blob = json.dumps([props["tickerLines"], props["lowerThirds"]])
    for term in find_banned(blob):
        problems.append(f"banned network name in overlays: {term}")
    if len(result["output_keys"]) < outputs:
        problems.append("missing output formats")
    expected = float(props["anchorDurationSeconds"])
    for key, a in result.get("analyses", {}).items():
        name = key.rsplit("/", 1)[-1]
        if abs(a["duration_s"] - expected) > max(1.0, 0.05 * expected):
            problems.append(f"{name}: length {a['duration_s']:.1f}s does not match the {expected:.1f}s anchor")
        if not a["has_audio"]:
            problems.append(f"{name}: no audio track")
        peak = a.get("true_peak_db")
        if peak is not None and peak > -0.1:
            problems.append(f"{name}: audio is clipping ({peak:.1f} dB)")
        av, aa = a.get("video_duration_s"), a.get("audio_duration_s")
        if av is not None and aa is not None and abs(av - aa) > 0.5:
            problems.append(f"{name}: audio and video lengths differ by {abs(av - aa):.1f}s")
    return problems


__all__ = ["Job", "LimitReached", "sm"]
