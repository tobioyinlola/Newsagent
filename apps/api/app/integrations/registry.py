"""Single place where concrete providers are chosen. Feature code calls these getters only."""

from app.config import get_settings
from app.integrations.avatar.base import AvatarProvider
from app.integrations.email.base import EmailProvider
from app.integrations.llm.base import ScriptLLM
from app.integrations.malware.base import MalwareScanner
from app.integrations.renderer.base import RendererClient
from app.integrations.storage.base import StorageProvider
from app.integrations.transcription.base import TranscriptionProvider

_cache: dict[str, object] = {}


def _get(name: str, factory):
    if name not in _cache:
        _cache[name] = factory()
    return _cache[name]


def reset_providers(**overrides: object) -> None:
    _cache.clear()
    _cache.update(overrides)


def override(**providers: object) -> None:
    """Replace specific providers (tests) without discarding the others."""
    _cache.update(providers)


def get_storage() -> StorageProvider:
    def make() -> StorageProvider:
        if get_settings().use_mocks:
            from app.integrations.storage.local import LocalStorage

            return LocalStorage(get_settings().local_storage_dir or None)
        from app.integrations.storage.r2 import R2Storage

        return R2Storage()

    return _get("storage", make)  # type: ignore[return-value]


def get_avatar() -> AvatarProvider:
    def make() -> AvatarProvider:
        if get_settings().use_mocks:
            from app.integrations.avatar.mock import MockAvatarProvider

            return MockAvatarProvider()
        from app.integrations.avatar.heygen import HeyGenProvider

        return HeyGenProvider()

    return _get("avatar", make)  # type: ignore[return-value]


def get_llm() -> ScriptLLM:
    def make() -> ScriptLLM:
        if get_settings().use_mocks:
            from app.integrations.llm.mock import MockScriptLLM

            return MockScriptLLM()
        from app.integrations.llm.anthropic import AnthropicScriptLLM

        return AnthropicScriptLLM()

    return _get("llm", make)  # type: ignore[return-value]


def get_renderer() -> RendererClient:
    def make() -> RendererClient:
        if get_settings().use_mocks and get_settings().renderer_backend != "http":
            from app.integrations.renderer.mock import MockRenderer

            return MockRenderer(get_storage())
        from app.integrations.renderer.http import HttpRenderer

        return HttpRenderer()

    return _get("renderer", make)  # type: ignore[return-value]


def get_email() -> EmailProvider:
    def make() -> EmailProvider:
        if get_settings().use_mocks:
            from app.integrations.email.mock import MockEmail

            return MockEmail()
        from app.integrations.email.resend import ResendEmail

        return ResendEmail()

    return _get("email", make)  # type: ignore[return-value]


def get_transcription() -> TranscriptionProvider:
    def make() -> TranscriptionProvider:
        if get_settings().use_mocks:
            from app.integrations.transcription.mock import MockTranscription

            return MockTranscription()
        from app.integrations.transcription.whisper_api import WhisperApiTranscription

        return WhisperApiTranscription()

    return _get("transcription", make)  # type: ignore[return-value]


def get_scanner() -> MalwareScanner:
    def make() -> MalwareScanner:
        if get_settings().use_mocks:
            from app.integrations.malware.mock import MockScanner

            return MockScanner()
        if not get_settings().clamd_host:
            raise RuntimeError("CLAMD_HOST must be set: uploads are refused without a malware scanner")
        from app.integrations.malware.clamav import ClamAvScanner

        return ClamAvScanner()

    return _get("scanner", make)  # type: ignore[return-value]


def get_billing():
    def make():
        from app.integrations.billing.mock import MockBilling

        if get_settings().billing_provider != "mock":
            raise RuntimeError("No payment provider adapter is configured. See docs/decisions.md.")
        return MockBilling()

    return _get("billing", make)
