"""A press release for a distribution request that has no video: written from details, or read from an uploaded file."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.db import get_session
from app.services import press_release as pr
from app.services.ratelimit import limit

router = APIRouter(prefix="/v1/distribution/press-release", tags=["distribution"])


class PressReleaseIn(BaseModel):
    kind: Literal["product_launch", "funding_round", "partnership", "hiring", "milestone", "other"] = "other"
    details: str = Field(min_length=20, max_length=4000)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: str = Field(min_length=1, max_length=100)
    company: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    website: str = Field(default="", max_length=300)

    @field_validator("details")
    @classmethod
    def _words(cls, v: str) -> str:
        if len(v.split()) > 250:
            raise ValueError("Keep the key details to 250 words.")
        return v


class PressReleaseOut(BaseModel):
    kind: str
    headline: str
    dek: str
    announcement: str
    unverified: list[str] = []


class ReadOut(BaseModel):
    headline: str
    announcement: str


@router.post("", response_model=PressReleaseOut, dependencies=[Depends(limit("press-release", 12, 3600))])
async def write_press_release(
    body: PressReleaseIn, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> dict:
    """Write a press release from the announcement's details. Nothing is saved or charged: the owner edits it, then chooses outlets."""
    return await pr.generate(session, body)


@router.post("/read", response_model=ReadOut, dependencies=[Depends(limit("press-release-read", 20, 3600))])
async def read_press_release(
    request: Request, filename: str = Query(min_length=1, max_length=200), p: Principal = Depends(current_principal)
) -> dict:
    """Read the text of a press release the business already has (the file's bytes are the request body). The file is not kept."""
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > pr.MAX_FILE_BYTES:
            raise HTTPException(413, "That file is larger than 2 MB.")
    try:
        text = pr.extract_text(filename, bytes(data))
    except pr.Unreadable as e:
        raise HTTPException(422, str(e)) from None
    headline, announcement = pr.split_release(text)
    return {"headline": headline, "announcement": announcement}
