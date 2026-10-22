import tempfile
from pathlib import Path

from app.config import get_settings
from app.integrations.storage.base import ObjectTooLarge, StorageProvider


class LocalStorage(StorageProvider):
    """Filesystem storage for local dev and tests. URLs point at the API's dev-only storage route."""

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or tempfile.mkdtemp(prefix="newsagent-store-"))

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("invalid storage key")
        return p

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    async def get(self, key: str, max_bytes: int) -> bytes:
        p = self.path(key)
        if p.stat().st_size > max_bytes:
            raise ObjectTooLarge(key)
        return p.read_bytes()

    async def size(self, key: str) -> int | None:
        p = self.path(key)
        return p.stat().st_size if p.exists() else None

    async def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return self.path(key).exists()

    def _url(self, key: str) -> str:
        return f"{get_settings().api_public_url}/v1/dev-storage/{key}"

    def presign_get(self, key: str, expires_s: int = 900) -> str:
        return self._url(key)

    def presign_put(self, key: str, expires_s: int = 900) -> str:
        return self._url(key)

    def create_multipart(self, key: str, parts: int, expires_s: int = 3600) -> dict:
        return {"upload_id": "local", "part_urls": [f"{self._url(key)}?part={i + 1}" for i in range(parts)]}
