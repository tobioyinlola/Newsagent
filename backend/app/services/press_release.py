"""A press release for a distribution request that has no video behind it: written from the same details a video starts with, or read
from a file the business already has.

Nothing here is published or paid for. The result is a draft the owner edits before they choose outlets."""

import io
import re
import zipfile
from datetime import UTC, datetime
from xml.etree import ElementTree

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.services import guided, moderation_flow
from app.services.safety import find_banned

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 50_000  # what a distribution announcement can hold
ALLOWED = (".txt", ".md", ".docx", ".pdf")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class Unreadable(Exception):
    """The file can't be read as a press release; the message is safe to show."""


def _tidy(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").replace("﻿", "")
    text = re.sub(r"[ \t ]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _docx(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > 8 * 1024 * 1024:
                raise Unreadable("That document is too large to read. Paste the text instead.")
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError):
        raise Unreadable("That doesn't look like a Word (.docx) document.") from None
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise Unreadable("That document can't be read safely. Paste the text instead.")
    try:
        root = ElementTree.fromstring(xml)  # noqa: S314 (DOCTYPE and entities were refused above)
    except ElementTree.ParseError:
        raise Unreadable("That document couldn't be read. Paste the text instead.") from None
    paragraphs = []
    for p in root.iter(f"{_W}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag in (f"{_W}tab", f"{_W}br"):
                parts.append(" ")
        paragraphs.append("".join(parts).strip())
    return "\n\n".join(paragraphs)


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    if not data.startswith(b"%PDF-"):
        raise Unreadable("That doesn't look like a PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise Unreadable("That PDF is password-protected. Paste the text instead.")
        if len(reader.pages) > 30:
            raise Unreadable("That PDF is too long for a press release. Paste the text instead.")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except Unreadable:
        raise
    except (PyPdfError, ValueError, KeyError, OSError, RecursionError):
        raise Unreadable("That PDF couldn't be read. Paste the text instead.") from None
    return "\n\n".join(p for p in pages if p)


def extract_text(filename: str, data: bytes) -> str:
    """The text of an uploaded press release (.txt, .md, .docx or .pdf)."""
    name = (filename or "").lower().strip()
    if not name.endswith(ALLOWED):
        raise Unreadable("Upload a Word (.docx), PDF, text (.txt) or Markdown (.md) file.")
    if not data:
        raise Unreadable("That file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise Unreadable("That file is larger than 2 MB.")
    if name.endswith(".docx"):
        text = _docx(data)
    elif name.endswith(".pdf"):
        text = _pdf(data)
    else:
        text = data.decode("utf-8", errors="replace")
    text = _tidy(text)
    if len(text) < 20:
        raise Unreadable("We couldn't find any text in that file. If it is a scan, paste the text instead.")
    if len(text) > MAX_TEXT_CHARS:
        raise Unreadable("That press release is too long. Shorten it, or paste the part you want to send.")
    return text


def split_release(text: str) -> tuple[str, str]:
    """A press release's headline (its first short line, after any 'FOR IMMEDIATE RELEASE') and the rest."""
    lines = [ln.strip() for ln in text.split("\n")]
    while lines and (not lines[0] or re.match(r"^for immediate release\b", lines[0], re.I)):
        lines.pop(0)
    if lines and len(lines[0]) <= 200 and len(lines) > 1:
        return lines[0], _tidy("\n".join(lines[1:]))
    return "", _tidy("\n".join(lines))


async def generate(session: AsyncSession, body) -> dict:
    """Write the press release from the details. Free, like the story of a video; it only becomes part of a request when the owner sends one."""
    kind = guided.TYPES.get(body.kind, "Other news")
    brief = guided.brief_from_details(body.kind, body.details)
    banned = find_banned(brief)
    if banned:
        raise HTTPException(
            422,
            {"error": "banned_network_name", "message": "Please remove real news network names: " + ", ".join(banned)},
        )
    verdict = await moderation_flow.evaluate(session, brief)
    if verdict.level == "block" and await moderation_flow.mode(session) == "enforce":
        raise HTTPException(
            422, {"error": "content_blocked", "message": "We can't write a press release from those details."}
        )
    llm = registry.get_llm()
    website = body.website.strip() or None
    founder = f"{body.first_name.strip()} {body.last_name.strip()}".strip()
    facts = {
        **await llm.parse_brief(brief, website),
        "founder_name": founder,
        "founder_title": f"{body.role.strip()}, {body.company.strip()}",
        "company": body.company.strip(),
        "website": website,
    }
    draft = None
    for attempt in range(2):  # the writer occasionally returns a malformed draft: one more try, then say so plainly
        try:
            draft = await llm.write_story(facts, body.kind, [])
            break
        except ValidationError:
            if attempt:
                raise HTTPException(
                    502, "We couldn't finish writing your press release just now. Please try again."
                ) from None
    assert draft is not None
    sections = guided._unrepeated_sections([s.model_dump() for s in draft.sections])
    paragraphs = [p.strip() for sec in sections for p in sec["paragraphs"] if p.strip()]
    now = datetime.now(UTC)
    place = ", ".join(x.strip().upper() for x in (body.city, body.country) if x.strip())
    dateline = f"{place} — {now:%B} {now.day}, {now.year}" if place else f"{now:%B} {now.day}, {now.year}"
    if paragraphs:
        paragraphs[0] = f"{dateline} — {paragraphs[0]}"
    about = (draft.about or "").strip()
    if about:
        paragraphs.append(f"About {body.company.strip()}\n{about}")
    return {
        "kind": kind,
        "headline": draft.headline.strip(),
        "dek": draft.dek.strip(),
        "announcement": "\n\n".join(paragraphs)[:MAX_TEXT_CHARS],
        "unverified": list(draft.unverified),
    }
