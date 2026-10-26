"""LiveKit for the AI interview: the room the founder joins and the token that lets one browser in.

Optional. Without the three LiveKit settings nothing here runs and the interview works exactly as before, in the browser alone.
The interviewer's voice is a small agent (agent/interviewer.py) that LiveKit starts when the founder joins; it speaks the same
scripted lines and costs one text-to-speech call per line. It never calls a language model.
"""

import json
from datetime import timedelta

from livekit import api

from app.config import get_settings

TOKEN_TTL = timedelta(hours=1)  # an interview is at most 5 minutes; this covers setup and a redo


def enabled() -> bool:
    s = get_settings()
    return bool(s.livekit_url and s.livekit_api_key and s.livekit_api_secret)


def room_name(project_id: str) -> str:
    return f"interview-{project_id}"


def mint_token(*, project_id: str, identity: str, name: str, interview_token: str, api_url: str) -> str:
    """A join token for this project's room only. It also asks LiveKit to start the interviewer agent in the room, and hands that
    agent what it needs to read the interview's lines from our API."""
    s = get_settings()
    meta = json.dumps({"api": api_url.rstrip("/"), "token": interview_token})
    return (
        api.AccessToken(s.livekit_api_key, s.livekit_api_secret)
        .with_identity(identity)
        .with_name(name)
        .with_ttl(TOKEN_TTL)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name(project_id),
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_room_config(
            api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=s.livekit_agent_name, metadata=meta)])
        )
        .to_jwt()
    )
