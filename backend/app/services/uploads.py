"""Upload validation: declared type/size are untrusted, so we check the real bytes after upload."""

import re
from dataclasses import dataclass

MB = 1024 * 1024


@dataclass(frozen=True)
class UploadRule:
    types: dict[str, str]  # content type -> file extension
    max_bytes: int


RULES: dict[str, UploadRule] = {
    "logo_light": UploadRule({"image/svg+xml": "svg", "image/png": "png"}, 2 * MB),
    "logo_dark": UploadRule({"image/svg+xml": "svg", "image/png": "png"}, 2 * MB),
    "guide_pdf": UploadRule({"application/pdf": "pdf"}, 10 * MB),
    "product_image": UploadRule({"image/png": "png", "image/jpeg": "jpg"}, 5 * MB),
    "product_video": UploadRule({"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}, 100 * MB),
    "presenter_clip": UploadRule({"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}, 150 * MB),
}

_SVG_DANGER = re.compile(
    rb"<\s*script|javascript:|\son[a-z]+\s*=|<\s*foreignobject|<\s*iframe|<\s*embed|<!entity|(?:xlink:)?href\s*=\s*[\"']\s*(?:https?:|//|data:text)",
    re.I,
)
_PDF_DANGER = re.compile(rb"/JavaScript|/JS\b|/Launch|/EmbeddedFile", re.I)


class InvalidUpload(Exception):
    pass


def validate_content(content_type: str, data: bytes) -> None:
    """Raise InvalidUpload unless the bytes really are the declared type and carry no active content."""
    if content_type == "image/png":
        ok = data.startswith(b"\x89PNG\r\n\x1a\n")
    elif content_type == "image/jpeg":
        ok = data.startswith(b"\xff\xd8\xff")
    elif content_type in {"video/mp4", "video/quicktime"}:
        ok = data[4:8] == b"ftyp"
    elif content_type == "video/webm":
        ok = data.startswith(b"\x1a\x45\xdf\xa3")
    elif content_type == "application/pdf":
        ok = data.startswith(b"%PDF-") and not _PDF_DANGER.search(data)
    elif content_type == "image/svg+xml":
        head = data[:2048].lstrip().lower()
        ok = (
            (head.startswith(b"<svg") or head.startswith(b"<?xml") or head.startswith(b"<!doctype svg"))
            and b"<svg" in data[:4096].lower()
            and not _SVG_DANGER.search(data)
        )
    else:
        ok = False
    if not ok:
        raise InvalidUpload("The file isn't a valid, safe " + content_type.split("/")[-1].upper() + ".")
