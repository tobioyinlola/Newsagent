from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    def presign_get(self, key: str, expires_s: int = 900) -> str: ...

    @abstractmethod
    def presign_put(self, key: str, expires_s: int = 900) -> str: ...

    @abstractmethod
    def create_multipart(self, key: str, parts: int, expires_s: int = 3600) -> dict:
        """Return {upload_id, part_urls[]} for resumable browser uploads."""
