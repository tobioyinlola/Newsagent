"""The AI interviewer's voice in a LiveKit room.

Scripted on purpose: it speaks the interview's own lines when the page asks, and nothing else. There is no language model and no
speech-to-text, so a whole interview costs a few text-to-speech calls. (Answers are recorded and transcribed by the main app.)
If this process is down the page notices within a few seconds and the browser speaks the lines itself.

Run:  python interviewer.py start      (needs LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, TTS_API_KEY)
"""

import asyncio
import json
import logging
import os

import httpx
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.agents.voice.room_io import RoomInputOptions
from livekit.plugins import openai
from protocol import TOPIC, Budget, encode, parse

log = logging.getLogger("cf-interviewer")
server = AgentServer()


async def fetch_lines(meta: dict) -> dict[str, str]:
    """The interview's lines as text, from the main app, using the interview's own token."""
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{meta['api']}/v1/interview/{meta['token']}/lines")
        r.raise_for_status()
        return r.json()["lines"]


@server.rtc_session(agent_name=os.getenv("AGENT_NAME", "cf-interviewer"))
async def entrypoint(ctx: JobContext) -> None:
    meta = json.loads(ctx.job.metadata or "{}")
    lines = await fetch_lines(meta)
    await ctx.connect()
    session = AgentSession(
        tts=openai.TTS(
            model=os.getenv("TTS_MODEL", "gpt-4o-mini-tts"),
            voice=os.getenv("TTS_VOICE", "ash"),
            api_key=os.getenv("TTS_API_KEY") or None,
        )
    )
    await session.start(
        agent=Agent(instructions="You are the Cover Founder interviewer. You only speak the lines you are given."),
        room=ctx.room,
        room_input_options=RoomInputOptions(audio_enabled=False, video_enabled=False, text_enabled=False),
    )
    budget = Budget()
    inbox: asyncio.Queue[rtc.DataPacket] = asyncio.Queue()
    ctx.room.on("data_received", lambda pkt: inbox.put_nowait(pkt) if pkt.topic == TOPIC else None)

    async def tell(t: str, **fields: object) -> None:
        await ctx.room.local_participant.publish_data(encode(t, **fields), topic=TOPIC)

    await tell("ready")
    ctx.room.on("participant_connected", lambda _p: asyncio.ensure_future(tell("ready")))  # a page that joined late

    while True:
        pkt = await inbox.get()
        msg = parse(pkt.data)
        if msg is None:
            continue
        text = lines.get(msg["key"], "")
        if text and budget.take(text):
            await session.say(text, allow_interruptions=False, add_to_chat_ctx=False)
            await tell("said", key=msg["key"])
        else:
            await tell("refused", key=msg["key"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli.run_app(server)
