"""News Desk's contract only. The business interview/video format does not import this module."""

import math
import re

MAX_SECONDS = 60
INTRO_SECONDS = 5
OUTRO_SECONDS = 6
STING_SECONDS = 2
MAX_PRESENTER_SECONDS = MAX_SECONDS - INTRO_SECONDS - OUTRO_SECONDS - STING_SECONDS
ARTICLE_MIN_WORDS, ARTICLE_MAX_WORDS = 200, 300
SCRIPT_MIN_WORDS, SCRIPT_MAX_WORDS = 60, 95


def words(text: str) -> int:
    return len(re.findall(r"\S+", text.strip()))


def validate_copy(data: dict) -> None:
    count = words(data.get("body", ""))
    if not ARTICLE_MIN_WORDS <= count <= ARTICLE_MAX_WORDS:
        raise ValueError(f"The written story must contain 200–300 words (currently {count}).")
    count = words(data.get("presenter_script", ""))
    if not SCRIPT_MIN_WORDS <= count <= SCRIPT_MAX_WORDS:
        raise ValueError(
            f"The spoken presenter script must contain 60–95 words (currently {count}) to fit the one-minute video with intro and outro."
        )


def timeline(presenter_seconds: float) -> tuple[int, float]:
    if not math.isfinite(presenter_seconds) or presenter_seconds <= 0 or presenter_seconds > MAX_PRESENTER_SECONDS:
        raise ValueError(
            "The presenter recording exceeds the 47-second narration budget. Shorten the script and generate a new version; the recording will not be sped up or cut off."
        )
    frames = math.ceil(presenter_seconds * 30)
    total_frames = frames + (INTRO_SECONDS + OUTRO_SECONDS + STING_SECONDS) * 30
    if total_frames > MAX_SECONDS * 30:
        raise ValueError("The complete News Desk video must be no longer than 60 seconds.")
    return frames, total_frames / 30


def measured_output(
    duration: float, has_audio: bool, video_duration: float | None = None, audio_duration: float | None = None
) -> None:
    for value in (duration, video_duration, audio_duration):
        if value is not None and (not math.isfinite(value) or value <= 0 or value > MAX_SECONDS):
            raise ValueError(
                "The rendered News Desk video failed the strict 60-second maximum. It has not been published."
            )
    if not has_audio:
        raise ValueError("The News Desk video has no usable audio. It has not been published.")
