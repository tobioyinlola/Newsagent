"""The first-run questions after sign-up, and guided-tour progress. Used by customers and by back-office users alike."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.db import get_session
from app.models import User, Workspace
from app.services import onboarding as svc

router = APIRouter(prefix="/v1/me", tags=["onboarding"])


class ProfileIn(BaseModel):
    answers: dict = Field(default_factory=dict)  # only the questions on this card; the rest are left as they were
    step: int | None = Field(default=None, ge=0, le=20)
    status: str | None = None  # in_progress | done | skipped


class TourIn(BaseModel):
    step: int = Field(default=0, ge=0, le=100)
    done: bool = False
    dismissed: bool = False
    reset: bool = False  # start the tour again


async def _mine(p: Principal, db: AsyncSession) -> tuple[User, Workspace]:
    user = await db.get(User, p.user.id)
    ws = await db.get(Workspace, p.user.workspace_id)
    assert user is not None and ws is not None
    return user, ws


@router.get("/onboarding")
async def get_onboarding(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    user, ws = await _mine(p, db)
    return svc.state(user.onboarding, ws.profile)


@router.put("/onboarding/profile")
async def save_profile(
    body: ProfileIn, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)
) -> dict:
    """Save one card's answers, move on, or skip. Nothing here is required."""
    if body.status is not None and body.status not in svc.STATUSES:
        raise HTTPException(422, "Unknown status.")
    user, ws = await _mine(p, db)
    if p.is_operator:  # the team's own accounts are not customers: they have no business profile to fill in
        raise HTTPException(403, "These questions are for customer accounts.")
    answers = svc.clean_answers(body.answers)
    if answers:
        ws.profile = {**(ws.profile or {}), **answers}
    user.onboarding = svc.set_progress(user.onboarding, status=body.status, step=body.step)
    await db.commit()
    return svc.state(user.onboarding, ws.profile)


@router.put("/tours/{tour_id}")
async def save_tour(
    tour_id: str, body: TourIn, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)
) -> dict:
    """Remember how far this person got in a guided tour."""
    if not svc.TOUR_ID.match(tour_id):
        raise HTTPException(422, "Unknown tour.")
    user, ws = await _mine(p, db)
    try:
        user.onboarding = svc.set_tour(
            user.onboarding, tour_id, step=body.step, done=body.done, dismissed=body.dismissed, reset=body.reset
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    await db.commit()
    return svc.state(user.onboarding, ws.profile)
