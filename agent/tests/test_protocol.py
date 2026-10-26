import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from protocol import MAX_LINE_CHARS, MAX_ROOM_CHARS, Budget, encode, parse  # noqa: E402


def test_only_say_messages_with_a_key_are_understood():
    assert parse(encode("say", key="q0")) == {"t": "say", "key": "q0"}
    assert parse(b"not json") is None
    assert parse(json.dumps({"t": "say"})) is None
    assert parse(json.dumps({"t": "other", "key": "q0"})) is None
    assert parse(json.dumps([1, 2])) is None
    assert len(parse(encode("say", key="x" * 500))["key"]) == 20  # a key is never long


def test_a_room_cannot_run_up_the_voice_bill():
    b = Budget()
    assert not b.take("")
    assert not b.take("x" * (MAX_LINE_CHARS + 1))
    spoken = 0
    while b.take("y" * 300):
        spoken += 300
    assert spoken <= MAX_ROOM_CHARS and not b.take("y" * 300)
