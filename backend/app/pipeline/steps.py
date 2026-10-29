"""Pipeline steps. Each is idempotent (see runner.run_step) and every paid call goes through SpendGuard."""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import VENDOR_POLICIES, get_settings
from app.db import session_maker
from app.integrations import registry
from app.integrations.avatar.base import AvatarRequest
from app.integrations.errors import ProviderPending, classify
from app.integrations.renderer.base import RenderRequest
from app.models import Asset, BrandKit, InterviewSession, Job, Project, ScriptVersion, Take, Workspace
from app.services import cf_news, provider_requests
from app.services import presenter as clip_lib
from app.services import scene_plan as sp
from app.services import state_machine as sm
from app.services.captions import build_srt
from app.services.claims import detect_claims
from app.services.interview import answer_cues, merge_srt, parse_srt, shifted_cues
from app.services.notifications import low_balance_alert, notify_operators, vendor_budget_alert
from app.services.safety import find_banned
from app.services.spend_guard import LimitReached, SpendGuard

log = logging.getLogger("pipeline")

FORMATS = [
    {"kind": "video", "format": "16x9", "width": 1920, "height": 1080},
    {"kind": "video", "format": "9x16", "width": 1080, "height": 1920},
    {"kind": "thumbnail", "format": "16x9", "name": "thumbnail", "width": 1920, "height": 1080},
]
VERTICAL = "9x16"


def final_formats() -> list[dict]:
    """What the final render produces: widescreen and a thumbnail, plus vertical when RENDER_VERTICAL is on."""
    return [o for o in FORMATS if o["format"] != VERTICAL or get_settings().render_vertical]


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


FEATURE_INVITE = "If you'd like your business or founder story featured on Cover Founder, get in touch with us and we'll report on it."


def with_invite(text: str) -> str:
    """Every video ends by inviting viewers to get featured. The invitation goes just before a closing "thank you for
    watching" line when there is one, otherwise at the very end; a text that already invites is left alone."""
    t = text.strip()
    if "featured on cover founder" in t.lower():
        return t
    if not t:
        return FEATURE_INVITE
    head, sep, last = t.rpartition(". ")
    if sep and "watching" in last.lower():
        return f"{head}. {FEATURE_INVITE} {last}"
    return f"{t} {FEATURE_INVITE}"


def anchor_text(script: ScriptVersion) -> str:
    return " ".join(s["text"] for s in script.segments)


def presenter_only_text(script: ScriptVersion) -> str:
    """What the presenter says in a presenter-only video: the whole script, ending with the invitation to get featured."""
    return with_invite(anchor_text(script))


def _fullframe_entries() -> dict[str, bool]:
    """Configured studio-in-picture looks, as {look id: needs our boards over its picture}. Write `id:plain` for a picture that has no
    screens or reflections to cover (a plain newsroom behind the presenter)."""
    out: dict[str, bool] = {}
    for item in get_settings().heygen_fullframe_avatar_ids.split(","):
        look, _, flag = item.strip().partition(":")
        if look:
            out[look] = flag.strip() != "plain"
    return out


def is_fullframe(project: Project) -> bool:
    """Does this project's presenter video already contain its own studio (so it is shown full frame, not cut out)?"""
    return avatar_for(project) in _fullframe_entries()


def fullframe_covers(project: Project) -> bool:
    return _fullframe_entries().get(avatar_for(project) or "", True)


def clip_ext(project: Project) -> str:
    return (
        "mp4" if is_fullframe(project) else "webm"
    )  # a studio-in-picture look is plain video; a cut-out keeps its alpha


def avatar_for(project: Project) -> str | None:
    """The presenter look to ask the vendor for: the project's choice, else the configured default."""
    return project.anchor_id or get_settings().heygen_default_avatar_id or None


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
        "text": presenter_only_text(script),
        "accent": project.voice_accent,
        "anchor": avatar_for(project),
        "accent_override": project.accent_override,
    }


def published_label(now: datetime | None = None) -> str:
    """The date and time stamp on the video, news-channel style: 'OCT 29, 2026 · 10:42 AM EDT', in the channel's own time zone."""
    from datetime import tzinfo
    from zoneinfo import ZoneInfo

    tz: tzinfo
    try:
        tz = ZoneInfo(get_settings().live_timezone)
    except Exception:  # a mistyped zone must never fail a render
        tz = UTC
    t = (now or datetime.now(UTC)).astimezone(tz)
    return f"{t:%b} {t.day}, {t.year} · {t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'} {t.tzname()}".upper()


BRAND_INTRO_S, BRAND_OUTRO_S = 5.0, 6.0  # keep in step with renderer/src/compositions/brand.ts


def brand_lead() -> float:
    """Seconds of branded opening before the video proper (captions and the thumbnail skip it)."""
    return BRAND_INTRO_S if get_settings().brand_cards else 0.0


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
        "studio": project.studio_id,  # which studio set to draw; "default" is the bright blue news studio
        "anchorFullFrame": is_fullframe(project),  # the presenter video brings its own studio
        "anchorCovers": fullframe_covers(
            project
        ),  # draw our boards over that picture's screens (false for a plain newsroom)
        "anchorDurationSeconds": anchor_duration_s,
        "tickerLines": [*script.ticker_lines, *await cf_news.ticker_items(session, exclude_project=project.id)],
        "lowerThirds": script.lower_thirds,
        "liveLocation": get_settings().live_location,
        "publishedLabel": published_label(),
        "brandCards": get_settings().brand_cards,
        "brandIntroSeconds": brand_lead(),
        "brandOutroSeconds": BRAND_OUTRO_S if get_settings().brand_cards else 0.0,
    }


RENDER_LINK_S = 6 * 3600  # links handed to the renderer outlive a long render (it also downloads them first)
MAX_VIDEO_DOWNLOAD_BYTES = 600 * 1024 * 1024


async def persist_avatar_video(key: str, out) -> None:
    """Copy the vendor's video into our own storage (vendor URLs expire; the renderer reads from our bucket).
    Green-screen output (e.g. Synthesia) is keyed to a transparent WebM by the renderer first."""
    storage = registry.get_storage()
    url = out.video_url
    raw_key = f"{key}.src.mp4" if out.needs_chroma_key else key
    ctype = "video/mp4" if key.endswith(".mp4") else "video/webm"
    if url.startswith("mock://"):
        from pathlib import Path

        from app.config import get_settings

        f = get_settings().mock_anchor_file
        await storage.put(raw_key, Path(f).read_bytes() if f else b"mock-anchor-video", ctype)
    else:
        import httpx

        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as c:
            r = await c.get(url)
            r.raise_for_status()
            if len(r.content) > MAX_VIDEO_DOWNLOAD_BYTES:
                raise RuntimeError("anchor video too large")
            await storage.put(raw_key, r.content, ctype)
    if out.needs_chroma_key:
        try:
            await registry.get_renderer().chroma_key(storage.presign_get(raw_key, 1800), key)
        finally:
            await storage.delete(raw_key)  # never keep the un-keyed copy


_failover_notified: dict[str, float] = {}


async def _is_cancelled(project_id: str) -> bool:
    async with session_maker()() as s:
        p = await s.get(Project, project_id)
        return p is None or p.state == "cancelled"


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
        pr_id: str | None = None
        try:
            if avatar.supports_async:
                # the hold and the request row are committed together BEFORE the vendor is called; the vendor's id is
                # recorded the moment it is issued. A crash, retry or duplicate run resumes that job and that hold
                # instead of buying a second video.
                rh = input_hash(
                    {
                        "text": req.script_text,
                        "accent": req.voice_accent,
                        "avatar": req.avatar_id,
                        "glossary": req.pronunciation,
                        "transparent": req.transparent,
                        "voice": voice_tag(),
                    }
                )
                pr_id, res = await provider_requests.begin(
                    session, guard, avatar, req, project=project, slot=key, request_hash=rh, stage=stage
                )
            else:
                res = await guard.reserve(
                    project.workspace_id, avatar.name, avatar.estimate_cost(req), project_id=project.id, stage=stage
                )
        except LimitReached as e:
            if e.code == "vendor_budget" and more:  # this provider's monthly budget is spent: use the next one
                last = e
                continue
            raise
        try:
            if pr_id:
                out = await provider_requests.generate(
                    avatar,
                    req,
                    project_id=project.id,
                    slot=key,
                    request_hash=rh,
                    policy=VENDOR_POLICIES["avatar"],
                    is_cancelled=lambda: _is_cancelled(project.id),
                )
            else:
                out = await avatar.generate(req)
            await persist_avatar_video(key, out)
        except (provider_requests.Cancelled, ProviderPending):
            # nothing failed: the vendor is still working (or the owner stopped the project). The hold stays with the
            # request row and is reused when the work resumes.
            if not pr_id:
                await guard.release(res)
            raise
        except Exception as e:  # noqa: BLE001
            if pr_id and await provider_requests.in_flight(pr_id):
                raise  # the vendor job is still running (e.g. a network blip while waiting): keep the hold, retry resumes
            await guard.release(res)
            if pr_id:
                await provider_requests.clear_hold(session, pr_id)
                await session.commit()  # the hold was committed in begin(), so its release must be too
            last = e
            log.warning("avatar provider %s failed for %s: %s", avatar.name, stage, e)
            if more and classify(e).category != "busy":
                k = f"{avatar.name}->{chain[i + 1].name}"
                if time.time() - _failover_notified.get(k, 0) > 3600:  # one email an hour, not one per clip
                    _failover_notified[k] = time.time()
                    await notify_operators(
                        f"Avatar failover: {avatar.name} failed",
                        f"{avatar.name} failed ({str(e)[:200]}). Switching to {chain[i + 1].name} for this clip.",
                    )
                continue
            raise
        cost = await guard.settle(res, out.cost)
        if pr_id:
            await provider_requests.clear_hold(session, pr_id)  # settled: committed with the clip that it paid for
        return out, cost, avatar.name
    assert last is not None
    raise last


async def _reuse_clip(session: AsyncSession, project: Project, *, atype: str, fmt: str, h: str, key: str) -> bool:
    """Copy an identical clip (same words, presenter, voice and pronunciation) made for an earlier project, so a fixed
    line such as the sign-off is bought from the vendor once, not once per video. Returns False if there is none."""
    storage = registry.get_storage()
    ext = key.rsplit(".", 1)[-1]
    sources = (
        await session.execute(
            select(Asset)
            .where(Asset.type == atype, Asset.hash == h, Asset.project_id != project.id, Asset.duration.is_not(None))
            .order_by(Asset.created_at.desc())
            .limit(5)
        )
    ).scalars()
    for src in sources:
        if src.storage_key.rsplit(".", 1)[-1] != ext:
            continue
        try:
            data = await storage.get(src.storage_key, MAX_VIDEO_DOWNLOAD_BYTES)
        except Exception:  # noqa: BLE001  the earlier copy was deleted (e.g. its owner erased the project)
            continue
        await storage.put(key, data, "video/mp4" if ext == "mp4" else "video/webm")
        for old in (
            await session.execute(
                select(Asset).where(Asset.project_id == project.id, Asset.type == atype, Asset.format == fmt)
            )
        ).scalars():
            await session.delete(old)
        session.add(
            Asset(project_id=project.id, type=atype, format=fmt, storage_key=key, hash=h, duration=src.duration)
        )
        await session.commit()
        log.info("reused presenter clip %s/%s from an earlier project (no vendor cost)", atype, fmt)
        return True
    return False


def closing_params() -> dict | None:
    """Optional vendor fields for the sign-off clip (HEYGEN_CLOSING_PARAMS, a JSON object), so its expression can be set."""
    raw = get_settings().heygen_closing_params.strip()
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        log.warning("HEYGEN_CLOSING_PARAMS is not valid JSON; ignored")
        return None
    return data if isinstance(data, dict) and data else None


def voice_tag() -> str:
    """Part of every presenter clip's identity: a clip made with one voice is never reused once the voices are changed."""
    st = get_settings()
    return f"{st.heygen_voice_male}|{st.heygen_voice_female}|{st.heygen_default_voice_id}|v2"


async def _paid_avatar_asset(
    session: AsyncSession,
    project: Project,
    guard: SpendGuard,
    *,
    atype: str,
    fmt: str,
    text: str,
    key: str,
    add_cost: bool = True,
) -> Decimal:
    """Generate one anchor clip unless an identical one already exists. Commits as it goes so a later failure
    never makes a retry pay for this clip again. Returns the cost it recorded on the project."""
    kit = await current_kit(session, project.workspace_id)
    glossary = (kit.pronunciation_glossary if kit else None) or None
    h = input_hash(
        {
            "text": text,
            "accent": project.voice_accent,
            "avatar": avatar_for(project),
            "glossary": glossary,
            "voice": voice_tag(),
        }
    )
    existing = (
        await session.execute(
            select(Asset.id).where(
                Asset.project_id == project.id, Asset.type == atype, Asset.format == fmt, Asset.hash == h
            )
        )
    ).first()
    if existing:
        return Decimal("0")
    if await _reuse_clip(session, project, atype=atype, fmt=fmt, h=h, key=key):
        return Decimal("0")  # the same words by the same presenter were already paid for (e.g. the standard sign-off)
    req = AvatarRequest(
        script_text=text,
        pronunciation=glossary,
        voice_accent=project.voice_accent,
        avatar_id=avatar_for(project),
        transparent=not is_fullframe(project),
        extra=closing_params() if atype == "anchor_outro" else None,
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
    if add_cost:
        project.cost_total += cost
    await session.commit()
    return cost


PARALLEL_CLIPS = 3  # presenter clips made at once (the avatar vendor's own concurrency limit)


async def _paid_clips(session: AsyncSession, project: Project, guard: SpendGuard, jobs: list[dict]) -> Decimal:
    """Make several presenter clips at the same time, each in its own database session, so a video with four questions takes about
    as long as one clip rather than six in a row. Every clip commits as it finishes, so a failure never loses (or re-buys) the others.
    The first failure is raised once all of them have settled."""
    import asyncio

    if session.get_bind().dialect.name == "sqlite":  # one writer at a time (local development and tests)
        total = Decimal("0")
        for spec in jobs:
            total += await _paid_avatar_asset(session, project, guard, **spec)
        return total
    pid, wid = project.id, project.workspace_id
    gate = asyncio.Semaphore(PARALLEL_CLIPS)

    async def one(spec: dict) -> Decimal:
        async with gate, session_maker()() as s:
            p = await s.get(Project, pid)
            assert p is not None and p.workspace_id == wid
            g = SpendGuard(s, on_alert=vendor_budget_alert, on_low_balance=low_balance_alert)
            return await _paid_avatar_asset(s, p, g, add_cost=False, **spec)

    results = await asyncio.gather(*(one(j) for j in jobs), return_exceptions=True)
    total = sum((r for r in results if isinstance(r, Decimal)), Decimal("0"))
    if total:
        project.cost_total += total
    for r in results:
        if isinstance(r, BaseException):
            await session.commit()  # keep the cost of the clips that did finish
            raise r
    return total


EXTRA_KINDS = ("explanation", "analysis")


def segment_texts(script: ScriptVersion) -> dict[str, str]:
    """What the presenter says, by part. `explanation` plays right after the opening (before the interview), `analysis`
    after the founder's answers (before the closing). Segments of any other kind but "outro" are the opening."""

    def join(pred) -> str:
        return " ".join(sg["text"] for sg in script.segments if pred(sg.get("kind")))

    out = {
        "main": join(lambda k: k != "outro" and k not in EXTRA_KINDS),
        "explanation": join(lambda k: k == "explanation"),
        "analysis": join(lambda k: k == "analysis"),
        "outro": with_invite(join(lambda k: k == "outro")),  # every video signs off with the invitation to get featured
    }
    if not out["main"] and out["explanation"]:  # a script that only has an explanation: it is the opening
        out["main"], out["explanation"] = out["explanation"], ""
    return out


def split_segments(script: ScriptVersion) -> tuple[str, str]:
    """Interview cut: the anchor speaks the opening, then (after the interview) the outro."""
    t = segment_texts(script)
    return t["main"], t["outro"]


async def anchor_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    script = await approved_script(session, project.id)
    if project.interview_enabled:
        t = segment_texts(script)
        main, outro = t["main"], t["outro"]
        jobs = [
            dict(
                atype="anchor",
                fmt="main",
                text=main or anchor_text(script),
                key=f"projects/{project.id}/anchor.{clip_ext(project)}",
            )
        ]
        for part in EXTRA_KINDS:  # separate presenter clips only when the script has those parts
            if t[part]:
                jobs.append(
                    dict(
                        atype="anchor",
                        fmt=part,
                        text=t[part],
                        key=f"projects/{project.id}/anchor-{part}.{clip_ext(project)}",
                    )
                )
        if outro:
            jobs.append(
                dict(
                    atype="anchor_outro",
                    fmt="outro",
                    text=outro,
                    key=f"projects/{project.id}/anchor-outro.{clip_ext(project)}",
                )
            )
        total = await _paid_clips(session, project, guard, jobs)
        return StepOutcome({"split": True}, recorded_cost=total)
    kit = await current_kit(session, project.workspace_id)
    req = AvatarRequest(
        script_text=presenter_only_text(script),
        pronunciation=(kit.pronunciation_glossary if kit else None) or None,
        voice_accent=project.voice_accent,
        avatar_id=avatar_for(project),
        transparent=not is_fullframe(project),
    )
    key = f"projects/{project.id}/anchor.{clip_ext(project)}"
    out, cost, vendor = await generate_anchor(session, project, guard, req, key, "anchor")
    for old in (
        await session.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "anchor"))
    ).scalars():
        await session.delete(old)  # a revised script replaces the earlier presenter clip
    session.add(Asset(project_id=project.id, type="anchor", storage_key=key, duration=Decimal(str(out.duration_s))))
    return StepOutcome({"vendor": vendor, "duration_s": out.duration_s, "key": key}, cost)


def needed_questions(project: Project, count: int) -> list[int]:
    """Questions that need a presenter clip, in the order they play: only the answers the owner features. Every clip is
    paid for by the second, so an answer that is left out of the video never gets one."""
    plan = project.merge_plan
    if not plan:
        return list(range(count))
    include = {a["question_index"] for a in plan["answers"] if a.get("include", True)}
    return [q for q in plan.get("order", range(count)) if q in include and q < count]


def question_text(project: Project, script: ScriptVersion, q: int, needed: list[int]) -> str:
    """What the presenter says for a question. In the guided flow the first one hands the conversation to the founder."""
    text = script.interview_questions[q]
    if project.flow == "guided" and needed and q == needed[0]:
        return f"Let's hear from the founder. {text}"
    return text


async def question_clips(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    """One anchor clip per featured interview question (stage 8). Idempotent per question."""
    script = await approved_script(session, project.id)
    needed = needed_questions(project, len(script.interview_questions))
    total = await _paid_clips(
        session,
        project,
        guard,
        [
            dict(
                atype="question_clip",
                fmt=f"q{i}",
                text=question_text(project, script, i, needed),
                key=f"projects/{project.id}/question-{i}.{clip_ext(project)}",
            )
            for i in needed
        ],
    )
    return StepOutcome({"questions": len(needed)}, recorded_cost=total)


async def question_clips_complete(session: AsyncSession, project: Project) -> bool:
    script = await approved_script(session, project.id)
    needed = needed_questions(project, len(script.interview_questions))
    have = {
        a.format
        for a in (
            await session.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "question_clip"))
        ).scalars()
    }
    return all(f"q{i}" in have for i in needed)


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
    # A render can take many minutes. Commit now so no database row stays locked while it runs: an open transaction here
    # held the project and the workspace, which made "Cancel" (and other spending in the workspace) hang until it finished.
    await guard.session.commit()
    try:
        render_id = await renderer.submit(req)
        status = await _wait(renderer, render_id, project.id)
    except BaseException:
        await guard.release(res)
        await guard.session.commit()  # the release must survive the caller's rollback
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
    clips = await clip_lib.select_clips(
        session, project.id
    )  # the library's opening shot and sign-off frame the presenter
    storage = registry.get_storage()
    for field, c in (("introClip", clips.intro), ("outroClip", clips.outro)):
        if c is not None:
            props[field] = {"src": storage.presign_get(c.key, RENDER_LINK_S), "seconds": float(c.duration_s or 0)}
    status, cost = await _submit_render(
        guard,
        project,
        composition="NewsStudio",
        props=props,
        outputs=outputs,
        prefix=prefix,
        input_urls={"anchor": registry.get_storage().presign_get(anchor.storage_key, RENDER_LINK_S)},
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
    made = final_formats()
    if not any(o["format"] == VERTICAL for o in made):  # an older vertical file no longer matches this video
        for old in (
            await session.execute(
                select(Asset).where(Asset.project_id == project.id, Asset.type == "render", Asset.format == VERTICAL)
            )
        ).scalars():
            await session.delete(old)
    for o, key in zip(made, status.output_keys, strict=False):
        atype = "thumbnail" if o["kind"] == "thumbnail" else "render"
        for old in (  # a re-render replaces the previous version in place (same storage key)
            await session.execute(
                select(Asset).where(Asset.project_id == project.id, Asset.type == atype, Asset.format == o["format"])
            )
        ).scalars():
            await session.delete(old)
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
    script, anchor, props, status, cost = await _render(session, project, guard, final_formats(), "final")
    analyses = await _record_outputs(session, project, status)
    lead = float((props.get("introClip") or {}).get("seconds", 0))  # captions start after the opening shot
    shift = lead + brand_lead()
    srt = build_srt([{"text": presenter_only_text(script)}], float(anchor.duration or 60))  # exactly what is spoken
    if shift:
        srt = merge_srt([(a + shift, b + shift, t) for a, b, t in parse_srt(srt)])
    srt_key = await _store_srt(session, project, srt)
    safe = {k: v for k, v in props.items() if k not in {"introClip", "outroClip"}} | {
        "introSeconds": lead,
        "outroSeconds": float((props.get("outroClip") or {}).get("seconds", 0)),
    }  # no signed URLs in the DB
    return StepOutcome(
        {"props": safe, "output_keys": status.output_keys, "srt_key": srt_key, "analyses": analyses}, cost
    )


def default_plan(question_count: int, layout: str = "pip") -> dict:
    return {
        "layout": layout,
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


async def answers_recorded(session: AsyncSession, project: Project) -> bool:
    """Has every interview question got a usable answer already? (A revised video goes straight to the merge.)"""
    script = await approved_script(session, project.id)
    takes = await latest_takes(session, project.id)
    return bool(script.interview_questions) and all(
        (t := takes.get(q)) is not None and t.status in {"ready", "needs_retake"}
        for q in range(len(script.interview_questions))
    )


async def merge_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
    try:
        return await _merge_render(session, project, guard)
    except ValidationError as e:  # the plan itself is invalid: say which scene and why, not a stack trace
        raise sp.ScenePlanError(
            [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()[:3]]
        ) from None


async def _merge_render(session: AsyncSession, project: Project, guard: SpendGuard) -> StepOutcome:
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
    ws = await session.get(Workspace, project.workspace_id)
    founder = {
        "name": isession.founder_name if isession else "",
        "title": isession.founder_title if isession else "",
        "location": ", ".join(x.strip() for x in (ws.city, ws.country) if x and x.strip()) if ws else "",
    }

    texts = segment_texts(script)
    main_text, outro_text = texts["main"], texts["outro"]
    main_srt = build_srt([{"text": main_text or anchor_text(script)}], float(main.duration or 60))
    # real presenter footage from the library frames the AI presenter: an opening shot, cutaways between answers, a sign-off
    clips = await clip_lib.select_clips(session, project.id)

    def usable(q: int) -> bool:
        take, ans = takes.get(q), answers.get(q, {})
        qclip = assets.get(("question_clip", f"q{q}"))
        if (
            take is None
            or not ans.get("include", True)
            or take.status not in {"ready", "needs_retake"}
            or qclip is None
        ):
            return False
        return float(take.duration_s or 0) - ans.get("trim_start_s", 0) - ans.get("trim_end_s", 0) >= 1.0

    shown = [q for q in plan["order"] if usable(q)]
    layout = plan["layout"] if plan["layout"] in sp.LAYOUT_SCENE else "pip"
    scenes: list[sp.Scene] = []
    cues: list[tuple[float, float, str]] = []
    founder_claims: list[str] = []
    cursor = 0.0

    def add(**kw) -> sp.Scene:
        nonlocal cursor
        sc = sp.Scene(id=f"s{len(scenes) + 1}", order=len(scenes), **kw)
        scenes.append(sc)
        cursor += sc.duration_s
        return sc

    def clip_scene(c, role: str) -> None:
        add(
            type="presenter_clip",
            duration_s=float(c.duration_s or 0),
            asset=sp.AssetRef(kind="presenter_clip", key=c.key),
            headline=role,
            provenance="presenter_footage",
            transition="fade" if role == "opening shot" else "cut",
        )

    if clips.intro:
        clip_scene(clips.intro, "opening shot")
    start = cursor
    add(
        type="anchor_intro",
        duration_s=float(main.duration or 0),
        narration=main_text or anchor_text(script),
        asset=sp.AssetRef(kind="anchor", key=main.storage_key),
    )
    cues += [(a + start, b + start, t) for a, b, t in parse_srt(main_srt)]

    def presenter_part(part: str, scene_type: str) -> None:
        """An extra presenter clip (explanation before the interview, analysis after it), if the script has that part."""
        if not texts[part]:
            return
        ref = assets.get(("anchor", part))
        if ref is None:
            raise sp.ScenePlanError([f"the presenter's {part} hasn't been made yet"])
        at = cursor
        add(
            type=scene_type,
            duration_s=float(ref.duration or 0),
            narration=texts[part],
            asset=sp.AssetRef(kind="anchor", key=ref.storage_key),
        )
        cues.extend(
            (at + a, at + b, t) for a, b, t in parse_srt(build_srt([{"text": texts[part]}], float(ref.duration or 1)))
        )

    presenter_part("explanation", "anchor_explanation")
    for item in (
        [] if project.flow == "guided" else project.broll or []
    ):  # product footage (the guided video leaves the owner's pictures to the written story)
        add(
            type="product_broll",
            duration_s=float(item["seconds"]),
            headline=item.get("caption") or None,
            asset=sp.AssetRef(kind="broll_image" if item["kind"] == "image" else "broll_video", key=item["key"]),
            provenance="synthetic" if item.get("synthetic") else "owner_media",
        )
    for q in shown:
        take, ans, qclip = takes[q], answers.get(q, {}), assets[("question_clip", f"q{q}")]
        trim = float(ans.get("trim_start_s", 0))
        window = float(take.duration_s or 0) - trim - ans.get("trim_end_s", 0)
        qsec = float(qclip.duration or 0)
        qref = sp.AssetRef(kind="question_clip", key=qclip.storage_key)
        add(
            type="anchor_question",
            duration_s=qsec,
            narration=script.interview_questions[q],
            asset=qref,
            question_index=q,
            question=script.interview_questions[q],
        )
        cues.append((cursor - qsec, cursor, script.interview_questions[q]))
        answer_start = cursor
        if take.kind == "video" and take.processed_video_key:
            main_ref = sp.AssetRef(kind="take_video", key=take.processed_video_key)
        else:
            main_ref = sp.AssetRef(kind="take_audio", key=take.processed_audio_key or "")
        poster = (
            sp.AssetRef(kind="snapshot", key=take.snapshot_key)
            if take.snapshot_key
            else (
                sp.AssetRef(kind="photo", key=isession.photo_key)
                if isession and isession.photo_key and take.kind != "video"
                else None
            )
        )
        words = answer_cues(take.srt or "", take.transcript or "", trim, window)
        own = ans.get("layout")
        add(
            type=sp.LAYOUT_SCENE[own if own in sp.LAYOUT_SCENE else layout],
            duration_s=window,
            asset=main_ref,
            question_asset=qref,
            poster=poster,
            question_index=q,
            question=script.interview_questions[q],
            question_number=shown.index(q) + 1,
            total_questions=len(shown),
            founder=sp.Founder(**founder),
            headline=chyron_for(script, q),
            trim_start_s=trim,
            cues=[sp.Cue(**c) for c in words],
            provenance="founder_statement",  # the founder's own recorded words, never rewritten
        )
        cues += shifted_cues(take.srt or "", answer_start, trim, window)
        founder_claims += [
            f"Founder said (question {shown.index(q) + 1}): {f.text}" for f in detect_claims(take.transcript or "")
        ]
        if clips.cutaways and q != shown[-1]:  # a cutaway to the presenter between answers, never after the last one
            clip_scene(clips.cutaways[shown.index(q) % len(clips.cutaways)], "cutaway")
    presenter_part("analysis", "anchor_analysis")
    closing_at: float | None = None
    if outro:
        start = closing_at = cursor
        add(
            type="news_closing",
            duration_s=float(outro.duration or 0),
            narration=outro_text,
            asset=sp.AssetRef(kind="anchor", key=outro.storage_key),
        )
        cues += [
            (start + a, start + b, t)
            for a, b, t in parse_srt(build_srt([{"text": outro_text}], float(outro.duration or 1)))
        ]
    if clips.outro:
        clip_scene(clips.outro, "sign-off")

    scene_plan = sp.ScenePlan(
        project_id=project.id,
        script_version_id=script.id,
        layout=layout,
        scenes=scenes,
        captions=[sp.Caption(start=a, end=b, text=t) for a, b, t in cues if b > a],
        total_s=round(sum(sc.duration_s for sc in scenes), 3),
        unconfirmed_claims=founder_claims,
    )
    await sp.validate_assets(
        scene_plan, storage
    )  # missing media fails now, with a message, before any render time is spent
    project.scene_plan, project.scene_plan_hash = scene_plan.model_dump(mode="json"), scene_plan.hash()
    t_cursor = scene_plan.total_s
    scenes_out = sp.to_render_scenes(scene_plan, lambda k: storage.presign_get(k, RENDER_LINK_S))
    base = await build_overlay_props(session, project, script, t_cursor)
    site = project.brief.website_url if project.brief else None
    props = {
        **base,
        "layout": layout,
        "scenes": scenes_out,
        "totalSeconds": t_cursor,
        "headline": story_headline(script),
        "presenter": presenter_identity(project),
    }
    if site and closing_at is not None:  # shown in a corner while the presenter signs off
        props |= {"productUrl": display_url(site), "productUrlFromSeconds": closing_at}
    status, cost = await _submit_render(
        guard,
        project,
        composition="InterviewMerge",
        props=props,
        outputs=final_formats(),
        prefix="final",
        input_urls={},
    )
    analyses = await _record_outputs(session, project, status)
    srt_key = await _store_srt(
        session, project, merge_srt([(a + brand_lead(), b + brand_lead(), t) for a, b, t in cues])
    )
    safe_props = {k: v for k, v in props.items() if k != "scenes"} | {
        "sceneCount": len(scenes),
        "scenePlanHash": project.scene_plan_hash,
    }  # no signed URLs in the DB
    return StepOutcome(
        {"props": safe_props, "output_keys": status.output_keys, "srt_key": srt_key, "analyses": analyses}, cost
    )


def story_headline(script: ScriptVersion) -> str:
    """The headline bar under the presenter: the written story's headline, else the script's first lower third."""
    story = script.story or {}
    if story.get("headline"):
        return str(story["headline"])[:110]
    lts = script.lower_thirds or []
    return str(lts[0].get("title", "")) if lts else ""


def chyron_for(script: ScriptVersion, q: int) -> str:
    """The headline bar while the founder answers question q: a short line from what they said (written with the story),
    else the story's headline."""
    chyrons = (script.story or {}).get("chyrons") or {}
    return str(chyrons.get(str(q)) or story_headline(script))[:90]


PRESENTER_ROLES = {  # first name -> (name shown on screen, role shown under it)
    "marcus": ("Marcus Richard", "Lead BTN Director, CF"),
}


def presenter_identity(project: Project) -> dict:
    """The presenter's name box. The house presenter is Marcus Richard, Lead BTN Director, CF; another house presenter shows
    their first name as a CF presenter."""
    from app.services import presenters as pres

    look = avatar_for(project)
    first = next((p.name.split(",")[0].strip() for p in pres.featured() if p.id == look), "")
    if not first:
        return {"name": "", "title": ""}
    return dict(zip(("name", "title"), PRESENTER_ROLES.get(first.lower(), (first, "Presenter, CF")), strict=True))


def display_url(url: str) -> str:
    """The address as people would type it: no scheme, no "www.", no trailing slash."""
    u = url.strip()
    for prefix in ("https://", "http://"):
        if u.lower().startswith(prefix):
            u = u[len(prefix) :]
    return u.removeprefix("www.").rstrip("/")


async def merge_inputs(session: AsyncSession, project: Project) -> dict:
    takes = await latest_takes(session, project.id)
    return {
        "clips": (await clip_lib.select_clips(session, project.id)).ids,  # a changed library re-renders
        "broll": project.broll,
        "plan": project.merge_plan,
        "takes": {q: [t.id, t.status, str(t.duration_s)] for q, t in sorted(takes.items())},
    }


async def _wait(renderer, render_id: str, project_id: str | None = None):
    """Wait for a render. If the owner cancels the video meanwhile, stop the render too, so it frees the renderer."""
    import asyncio
    import time

    polls = 0
    deadline = time.monotonic() + VENDOR_POLICIES["renderer"].timeout_s
    while True:
        if time.monotonic() > deadline:
            await renderer.cancel(render_id)  # free the renderer; the retry submits a fresh render
            raise TimeoutError("The render took too long")
        st = await renderer.status(render_id)
        if st.status == "succeeded":
            return st
        if st.status == "failed":
            raise RuntimeError(st.error or "render failed")
        polls += 1
        if project_id and polls % 5 == 0 and await _is_cancelled(project_id):
            await renderer.cancel(render_id)
            raise provider_requests.Cancelled()
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
    expected = (
        float(props["anchorDurationSeconds"])
        + float(props.get("introSeconds", 0))
        + float(props.get("outroSeconds", 0))
        + float(props.get("brandIntroSeconds", 0))
        + float(props.get("brandOutroSeconds", 0))
    )
    for key, a in result.get("analyses", {}).items():
        name = key.rsplit("/", 1)[-1]
        if abs(a["duration_s"] - expected) > max(1.0, 0.05 * expected):
            problems.append(f"{name}: length {a['duration_s']:.1f}s does not match the {expected:.1f}s planned")
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
