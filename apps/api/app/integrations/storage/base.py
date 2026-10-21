from abc import ABC, abstractmethod


class ObjectTooLarge(Exception):
    pass


class StorageProvider(ABC):
    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...

    @abstractmethod
    async def get(self, key: str, max_bytes: int) -> bytes:
        """Read an object. Raises ObjectTooLarge if it exceeds max_bytes (without reading it all)."""

    @abstractmethod
    async def size(self, key: str) -> int | None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    def presign_get(self, key: str, expires_s: int = 900) -> str: ...

    @abstractmethod
    def presign_put(self, key: str, expires_s: int = 900) -> str: ...

    @abstractmethod
    def create_multipart(self, key: str, parts: int, expires_s: int = 3600) -> dict:
        """Return {upload_id, part_urls[]} for resumable browser uploads."""
