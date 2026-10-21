import tempfile
from pathlib import Path

from app.integrations.storage.base import StorageProvider


class LocalStorage(StorageProvider):
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or tempfile.mkdtemp(prefix="newsagent-store-"))

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    async def exists(self, key: str) -> bool:
        return (self.root / key).exists()

    def presign_get(self, key: str, expires_s: int = 900) -> str:
        return f"local://{key}?expires={expires_s}"

    def presign_put(self, key: str, expires_s: int = 900) -> str:
        return f"local://{key}?put&expires={expires_s}"

    def create_multipart(self, key: str, parts: int, expires_s: int = 3600) -> dict:
        return {"upload_id": "local", "part_urls": [f"local://{key}?part={i + 1}" for i in range(parts)]}
