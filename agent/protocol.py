"""The little language between the interview page and the interviewer agent, over a LiveKit data channel.

The page tells the agent which line to speak by its key ("greeting", "q0", "thanks", "closing"); the agent looks the text up in
the interview's own lines, so it can only ever say what that interview's script says. A budget caps what one room can spend on
text-to-speech. Pure functions only, so this is tested without LiveKit.
"""

import json

TOPIC = "cf.interview"
MAX_LINE_CHARS = 400  # no interview line is longer than this
MAX_ROOM_CHARS = 3000  # about 5 minutes of speaking; a stuck page cannot run up the voice bill


def parse(payload: bytes | str) -> dict | None:
    """A message from the page, or None if it isn't one of ours."""
    try:
        msg = json.loads(payload)
    except (ValueError, TypeError):
        return None
    if not isinstance(msg, dict) or msg.get("t") != "say" or not isinstance(msg.get("key"), str):
        return None
    return {"t": "say", "key": msg["key"][:20]}


def encode(t: str, **fields: object) -> bytes:
    return json.dumps({"t": t, **fields}).encode()


class Budget:
    """Characters of speech one room may use."""

    def __init__(self, limit: int = MAX_ROOM_CHARS) -> None:
        self.left = limit

    def take(self, text: str) -> bool:
        n = len(text)
        if n == 0 or n > MAX_LINE_CHARS or n > self.left:
            return False
        self.left -= n
        return True
