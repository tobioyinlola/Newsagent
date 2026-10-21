"""Local-development object storage over HTTP so browser uploads/downloads work without MinIO.

Only mounted when ENVIRONMENT=local and USE_MOCKS=true. Never exists in staging or production.
"""

from fastapi import APIRouter, HTTPException, Request, Response

from app.integrations import registry
from app.integrations.storage.local import LocalStorage

router = APIRouter(prefix="/v1/dev-storage", tags=["dev"])
MAX_BYTES = 25 * 1024 * 1024


def _store() -> LocalStorage:
    s = registry.get_storage()
    if not isinstance(s, LocalStorage):
        raise HTTPException(404)
    return s


@router.put("/{key:path}")
async def put_object(key: str, request: Request) -> dict:
    body = await request.body()
    if len(body) > MAX_BYTES:
        raise HTTPException(413)
    try:
        await _store().put(key, body)
    except ValueError:
        raise HTTPException(400, "invalid key") from None
    return {"ok": True}


@router.get("/{key:path}")
async def get_object(key: str) -> Response:
    try:
        data = await _store().get(key, MAX_BYTES)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404) from None
    media = "video/mp4" if key.endswith(".mp4") else "image/png" if key.endswith(".png") else "application/octet-stream"
    return Response(data, media_type=media)
