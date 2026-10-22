"""Pipeline steps. Each is idempotent (see runner.run_step) and every paid call goes through SpendGuard."""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.integrations.avatar.base import AvatarRequest
from app.integrations.renderer.base import RenderRequest
from app.models import Asset, BrandKit, InterviewSession, Job, Project, ScriptVersion, Take
from app.services import state_machine as sm
from app.services.captions import build_srt
from app.services.interview import merge_srt, parse_srt, shifted_cues
from app.services.notifications import notify_operators
from app.services.safety import find_banned
from app.services.spend_guard import LimitReached, SpendGuard

log = logging.getLogger("pipeline")

FORMATS = [
    {"kind": "video", "format": "16x9", "width": 1920, "height": 1080},
    {"kind": "video", "format": "9x16", "width": 1080, "height": 1920},
    {"kind": "thumbnail", "format": "16x9", "name": "thumbnail", "width": 1920, "height": 1080},
]
PREVIEW = [{"kind": "video", "format": "16x9", "name": "preview", "width": 1920, "height": 1080, "scale": 0.5}]

# Locked channel identity and mandatory disclosures (hard rules 1 and 2). Never user-editable.
CHANNEL_IDENTITY = {"name": "Cover Founder", "locked": True}
DISCLOSURES = {"tag": "Featured", "anchor": "AI-generated anchor"}


def input_hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class StepOutcome:
    result: dict
    cost: Decimal = Decimal("0")  # cost not yet added to project.cost_total (the runner adds it)
    recorded_cost: Decimal = Decimal("0")  # already added by the step itself (multi-call steps commit as they go)


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


MAX_VIDEO_DOWNLOAD_BYTES = 600 * 1024 * 1024


async def persist_avatar_video(key: str, out) -> None:
    """Copy the vendor's video into our own storage (vendor URLs expire; the renderer reads from our bucket).
    Green-screen output (e.g. Synthesia) is keyed to a transparent WebM by the renderer first."""
    storage = registry.get_storage()
    url = out.video_url
    raw_key = f"{key}.src.mp4" if out.needs_chroma_key else key
    if url.startswith("mock://"):
        from pathlib import Path

        from app.config import get_settings

        f = get_settings().mock_anchor_file
        await storage.put(raw_key, Path(f).read_bytes() if f else b"mock-anchor-video", "video/webm")
    else:
        import httpx

        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            if len(r.content) > MAX_VIDEO_DOWNLOAD_BYTES:
                raise RuntimeError("anchor video too large")
            await storage.put(raw_key, r.content, "video/webm")
    if out.needs_chroma_key:
        try:
            await registry.get_renderer().chroma_key(storage.presign_get(raw_key, 1800), key)
        finally:
            await storage.delete(raw_key)  # never keep the un-keyed copy


_failover_notified: dict[str, float] = {}


async def generate_anchor(
    session: AsyncSession, project: Project, guard: SpendGuard, req: AvatarRequest, key: str, stage: str
):
    """Make one anchor clip, trying each configured provider in turn (spec: retry, then fail over to the secondary).
    Each attempt reserves against its OWN vendor budget, and a failed attempt releases its hold, so a failover
    never double-charges. Returns (result, cost, vendor_used)."""
    import time

    chain = await registry.avatar_chain(session)
    last: Exception | None = None
    for i, avatar in enumerate(chain):
        more = i < len(chain) - 1
        try:
            res = await guard.reserve(
                project.workspace_id, avatar.name, avatar.estimate_cost(req), project_id=project.id, stage=stage
            )
        except LimitReached as e:
            if e.code == "vendor_budget" and more:  # this provider's monthly budget is spent: use the next one
                last = e
                continue
            raise
        try:
            out = await avatar.generate(req)
            await persist_avatar_video(key, out)
        except Exception as e:  # noqa: BLE001
            await guard.release(res)
            last = e
            log.warning("avatar provider %s failed for %s: %s", avatar.name, stage, e)
            if more:
                k = f"{avatar.name}->{chain[i + 1].name}"
                if time.time() - _failover_notified.get(k, 0) > 3600:  # one email an hour, not one per clip
                    _failover_notified[k] = time.time()
                    await notify_operators(
                        f"Avatar failover: {avatar.name} failed",
                        f"{avatar.name} failed ({str(e)[:200]}). Switching to {chain[i + 1].name} for this clip.",
                    )
                continue
            raise
        return out, await guard.settle(res, out.cost), avatar.name
    assert last is not None
    raise last


async def _paid_avatar_asset(
    session: AsyncSession, project: Project, guard: SpendGuard, *, atype: str, fmt: str, text: str, key: str
) -> Decimal:
    """Generate one anchor clip unless an identical one already exists. Commits as it goes so a later failure
    never makes a retry pay for this clip again. Returns the cost it recorded on the project."""
    kit = await current_kit(session, project.workspace_id)
    glossary = (kit.pronunciation_glossary if kit else None) or None
    h = input_hash({"text": text, "accent": project.voice_accent, "avatar": project.anchor_id, "glossary": glossary})
    existing = (
        await session.execute(
            select(Asset.id).where(
                Asset.project_id == project.id, Asset.type == atype, Asset.format == fmt, Asset.hash == h
            )
        )
    ).first()
    if existing:
        return Decimal("0")
    req = AvatarRequest(
        script_text=text,
        pronunciation=glossary,
        voice_accent=project.voice_accent,
        avatar_id=project.anchor_id,
        transparent=True,
    )
    out, cost, _vendor = await generate_anchor(session, project, guard, req, key, atype)
    # an older clip for the same slot (e.g. the owner edited a question) is replaced
    for old in (
        await session.execute(
            select(Asset).where(Asset.project_id == project.id, Asset.type == atype, Asset.format == fmt)
        )
    ).scalars():
        await session.delete(old)
    session.add(
        Asset(
            project_id=project.id,
            type=atype,
            format=fmt,
            storage_key=key,
            hash=h,
            duration=Decimal(str(out.duration_s)),
        )
    )
    project.cost_total += cost
    await session.commit()
    return cost


def split_segments(script: ScriptVersion) -> tuple[str, str]:
    """Interview cut: the anchor speaks intro+body, then (after the interview) the outro."""
    main = " ".join(s["text"] for s in script.segments if s.get("kind") != "outro")
    outro = " ".join(s["text"] for s in script.segments if s.get("kind") == "outro")
    return main, outro


async def anchor_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    script = await approved_script(session, project.id)
    if project.interview_enabled:
        main, outro = split_segments(script)
        total = await _paid_avatar_asset(
            session,
            project,
            guard,
            atype="anchor",
            fmt="main",
            text=main or anchor_text(script),
            key=f"projects/{project.id}/anchor.webm",
        )
        if outro:
            total += await _paid_avatar_asset(
                session,
                project,
                guard,
                atype="anchor_outro",
                fmt="outro",
                text=outro,
                key=f"projects/{project.id}/anchor-outro.webm",
            )
        return StepOutcome({"split": True}, recorded_cost=total)
    kit = await current_kit(session, project.workspace_id)
    req = AvatarRequest(
        script_text=anchor_text(script),
        pronunciation=(kit.pronunciation_glossary if kit else None) or None,
        voice_accent=project.voice_accent,
        avatar_id=project.anchor_id,
        transparent=True,
    )
    key = f"projects/{project.id}/anchor.webm"
    out, cost, vendor = await generate_anchor(session, project, guard, req, key, "anchor")
    session.add(Asset(project_id=project.id, type="anchor", storage_key=key, duration=Decimal(str(out.duration_s))))
    return StepOutcome({"vendor": vendor, "duration_s": out.duration_s, "key": key}, cost)


async def question_clips(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    """One anchor clip per interview question (stage 8). Idempotent per question."""
    script = await approved_script(session, project.id)
    total = Decimal("0")
    for i, q in enumerate(script.interview_questions):
        total += await _paid_avatar_asset(
            session,
            project,
            guard,
            atype="question_clip",
            fmt=f"q{i}",
            text=q,
            key=f"projects/{project.id}/question-{i}.webm",
        )
    return StepOutcome({"questions": len(script.interview_questions)}, recorded_cost=total)


async def question_clips_complete(session: AsyncSession, project: Project) -> bool:
    script = await approved_script(session, project.id)
    have = {
        a.format
        for a in (
            await session.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "question_clip"))
        ).scalars()
    }
    return all(f"q{i}" in have for i in range(len(script.interview_questions)))


async def _submit_render(
    guard: SpendGuard,
    project: Project,
    *,
    composition: str,
    props: dict,
    outputs: list[dict],
    prefix: str,
    input_urls: dict[str, str],
):
    renderer = registry.get_renderer()
    req = RenderRequest(
        composition=composition,
        props=props,
        outputs=outputs,
        input_urls=input_urls,
        output_prefix=f"projects/{project.id}/{prefix}",
    )
    res = await guard.reserve(
        project.workspace_id, "renderer", renderer.estimate_cost(req), project_id=project.id, stage=prefix
    )
    try:
        render_id = await renderer.submit(req)
        status = await _wait(renderer, render_id)
    except Exception:
        await guard.release(res)
        raise
    cost = await guard.settle(res, renderer.estimate_cost(req))
    return status, cost


async def _render(session: AsyncSession, project: Project, guard: SpendGuard, outputs: list[dict], prefix: str):
    script = await approved_script(session, project.id)
    anchor = (
        (await session.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "anchor")))
        .scalars()
        .first()
    )
    assert anchor is not None, "anchor asset must exist before rendering"
    props = await build_overlay_props(session, project, script, float(anchor.duration or 60))
    status, cost = await _submit_render(
        guard,
        project,
        composition="NewsStudio",
        props=props,
        outputs=outputs,
        prefix=prefix,
        input_urls={"anchor": registry.get_storage().presign_get(anchor.storage_key)},
    )
    return script, anchor, props, status, cost


async def preview_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    _, _, props, status, cost = await _render(session, project, guard, PREVIEW, "preview")
    session.add(Asset(project_id=project.id, type="preview", storage_key=status.output_keys[0], format="16x9"))
    return StepOutcome({"props": props, "output_keys": status.output_keys}, cost)


async def _record_outputs(session: AsyncSession, project: Project, status) -> dict:
    """Register rendered files as assets and measure each video for the quality gate."""
    renderer = registry.get_renderer()
    analyses = {}
    for o, key in zip(FORMATS, status.output_keys, strict=False):
        atype = "thumbnail" if o["kind"] == "thumbnail" else "render"
        session.add(Asset(project_id=project.id, type=atype, storage_key=key, format=o["format"]))
        if o["kind"] == "video":
            analyses[key] = asdict(await renderer.analyze(registry.get_storage().presign_get(key)))
    return analyses


async def _store_srt(session: AsyncSession, project: Project, srt: str) -> str:
    key = f"projects/{project.id}/final/captions.srt"
    await registry.get_storage().put(key, srt.encode(), "application/x-subrip")
    for old in (
        await session.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "caption"))
    ).scalars():
        await session.delete(old)
    session.add(Asset(project_id=project.id, type="caption", storage_key=key))
    return key


async def final_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    script, anchor, props, status, cost = await _render(session, project, guard, FORMATS, "final")
    analyses = await _record_outputs(session, project, status)
    srt_key = await _store_srt(session, project, build_srt(script.segments, float(anchor.duration or 60)))
    return StepOutcome(
        {"props": props, "output_keys": status.output_keys, "srt_key": srt_key, "analyses": analyses}, cost
    )


def default_plan(question_count: int) -> dict:
    return {
        "layout": "pip",
        "order": list(range(question_count)),
        "answers": [
            {"question_index": q, "include": True, "trim_start_s": 0, "trim_end_s": 0} for q in range(question_count)
        ],
    }


async def latest_takes(session: AsyncSession, project_id: str) -> dict[int, Take]:
    """The current take per question: the newest one that isn't superseded."""
    rows = (
        await session.execute(
            select(Take).where(Take.project_id == project_id, Take.status != "superseded").order_by(Take.created_at)
        )
    ).scalars()
    out: dict[int, Take] = {}
    for t in rows:
        out[t.question_index] = t
    return out


async def merge_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    """Stage 10: anchor intro, then per question [anchor asks -> founder answers (PiP/split)], then outro."""
    storage = registry.get_storage()
    script = await approved_script(session, project.id)
    assets = {
        (a.type, a.format): a
        for a in (await session.execute(select(Asset).where(Asset.project_id == project.id))).scalars()
    }
    main = assets.get(("anchor", "main")) or assets.get(("anchor", None))
    assert main is not None, "anchor must exist before merging"
    outro = assets.get(("anchor_outro", "outro"))
    takes = await latest_takes(session, project.id)
    n = len(script.interview_questions)
    plan = project.merge_plan or default_plan(n)
    answers = {a["question_index"]: a for a in plan["answers"]}
    isession = (
        (
            await session.execute(
                select(InterviewSession)
                .where(InterviewSession.project_id == project.id)
                .order_by(InterviewSession.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    founder = {"name": isession.founder_name if isession else "", "title": isession.founder_title if isession else ""}

    main_text, outro_text = split_segments(script)
    main_srt = build_srt([{"text": main_text or anchor_text(script)}], float(main.duration or 60))
    scenes: list[dict] = [
        {"type": "anchor", "src": storage.presign_get(main.storage_key), "seconds": float(main.duration or 0)}
    ]
    cues = [(a, b, t) for a, b, t in parse_srt(main_srt)]
    t_cursor = float(main.duration or 0)
    for q in plan["order"]:
        take, ans, qclip = takes.get(q), answers.get(q, {}), assets.get(("question_clip", f"q{q}"))
        if (
            take is None
            or not ans.get("include", True)
            or take.status not in {"ready", "needs_retake"}
            or qclip is None
        ):
            continue
        window = float(take.duration_s or 0) - ans.get("trim_start_s", 0) - ans.get("trim_end_s", 0)
        if window < 1.0:
            continue
        qsec = float(qclip.duration or 0)
        qsrc = storage.presign_get(qclip.storage_key)
        scenes.append({"type": "question", "src": qsrc, "seconds": qsec})
        cues.append((t_cursor, t_cursor + qsec, script.interview_questions[q]))
        t_cursor += qsec
        scene: dict = {
            "type": "answer",
            "seconds": window,
            "startFromSeconds": ans.get("trim_start_s", 0),
            "pipSrc": qsrc,
            "founder": founder,
            "src": None,
        }
        if take.kind == "video" and take.processed_video_key:
            scene["src"] = storage.presign_get(take.processed_video_key)
        else:
            scene["audioSrc"] = storage.presign_get(take.processed_audio_key or "")
            if isession and isession.photo_key:
                scene["photoSrc"] = storage.presign_get(isession.photo_key)
        scenes.append(scene)
        cues += shifted_cues(take.srt or "", t_cursor, ans.get("trim_start_s", 0), window)
        t_cursor += window
    if outro:
        scenes.append(
            {"type": "anchor", "src": storage.presign_get(outro.storage_key), "seconds": float(outro.duration or 0)}
        )
        cues += [
            (t_cursor + a, t_cursor + b, t)
            for a, b, t in parse_srt(build_srt([{"text": outro_text}], float(outro.duration or 1)))
        ]
        t_cursor += float(outro.duration or 0)

    base = await build_overlay_props(session, project, script, t_cursor)
    props = {**base, "layout": plan["layout"], "scenes": scenes, "totalSeconds": t_cursor}
    status, cost = await _submit_render(
        guard, project, composition="InterviewMerge", props=props, outputs=FORMATS, prefix="final", input_urls={}
    )
    analyses = await _record_outputs(session, project, status)
    srt_key = await _store_srt(session, project, merge_srt(cues))
    safe_props = {k: v for k, v in props.items() if k != "scenes"} | {
        "sceneCount": len(scenes)
    }  # no signed URLs in the DB
    return StepOutcome(
        {"props": safe_props, "output_keys": status.output_keys, "srt_key": srt_key, "analyses": analyses}, cost
    )


async def merge_inputs(session: AsyncSession, project: Project) -> dict:
    takes = await latest_takes(session, project.id)
    return {
        "plan": project.merge_plan,
        "takes": {q: [t.id, t.status, str(t.duration_s)] for q, t in sorted(takes.items())},
    }


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
