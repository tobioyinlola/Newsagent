"""The words that join the programme together: how the presenter welcomes the guest, moves from one answer to the next question,
and rounds off. Written here (not by the language model) so they are never the same on every video and never repeat inside one.

Each video picks its own lines from the pools below, starting at a place decided by the video's id, so two videos made the same
day greet and bridge differently while a given video always gets the same lines (a retried step orders the same clips).

Every line is short. The presenter's words are paid for by the second, and these replace the generic "let's hear from the founder"
hand-over and the long invitation the closing used to carry: a whole video now has fewer presenter words than before.
"""

import hashlib

# Said before the first question. {name} is the guest's first name; the variants without it are used when we don't have one.
WELCOMES = [
    "{name}, welcome to our studio at Cover Founder. We're excited to have you here.",
    "{name}, thanks for joining us in the studio today. It's great to have you.",
    "Welcome to the Cover Founder studio, {name}. We're glad you're here.",
    "{name}, it's a pleasure to have you with us in the studio.",
    "Good to have you with us, {name}. Welcome to Cover Founder.",
    "{name}, thank you for coming into the studio. Let's get right into it.",
]
WELCOMES_NO_NAME = [
    "Welcome to our studio at Cover Founder. We're excited to have you here.",
    "Thanks for joining us in the studio today. It's great to have you.",
    "Welcome to the Cover Founder studio. We're glad you're here.",
    "It's a pleasure to have you with us in the studio.",
    "Good to have you with us. Welcome to Cover Founder.",
    "Thank you for coming into the studio. Let's get right into it.",
]

# Said between an answer and the next question: a short, genuine acknowledgement, then straight into the question.
BRIDGES = [
    "That's great, thanks for the insight.",
    "Really interesting, thank you for that.",
    "Thanks for sharing that.",
    "That's helpful, thank you.",
    "Great answer, thank you.",
    "That's a strong point, thanks.",
    "I appreciate you explaining that.",
    "Thank you, that really helps us understand.",
    "That's good to hear.",
    "Thanks, that gives us a clear picture.",
]
# Before the last question.
LAST_BRIDGES = [
    "Thank you, that's helpful. One last question.",
    "Great, thanks for that. And finally,",
    "That's really useful. One more for you.",
    "Thanks for sharing that. To finish,",
]


def _seed(project_id: str) -> int:
    return int(hashlib.sha256(project_id.encode()).hexdigest()[:8], 16)


def first_name(full_name: str | None) -> str:
    parts = (full_name or "").split()
    return parts[0].strip(",.") if parts else ""


def welcome(project_id: str, founder_name: str | None) -> str:
    name = first_name(founder_name)
    pool = WELCOMES if name else WELCOMES_NO_NAME
    line = pool[_seed(project_id) % len(pool)]
    return line.format(name=name) if name else line


def bridges(project_id: str, count: int) -> list[str]:
    """`count` acknowledgements for the gaps between questions (the last one leads into the final question). Distinct within a video."""
    if count <= 0:
        return []
    seed = _seed(project_id)
    # a step of 3 through ten lines never lands on the same one twice before ten are used
    middle = [BRIDGES[(seed + 3 * i) % len(BRIDGES)] for i in range(count - 1)]
    return middle + [LAST_BRIDGES[seed % len(LAST_BRIDGES)]]
