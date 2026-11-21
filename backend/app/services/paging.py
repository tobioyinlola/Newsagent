"""One way to page every list: `limit` and `offset` in the address, and the total number of rows back.

A list that returns an array sends the total in the `X-Total-Count` header; a list that returns an object carries `total`, `limit` and
`offset` beside its items. Either way no list can ever return an unbounded number of rows: every one has a default and a hard maximum."""

from dataclasses import dataclass

from fastapi import Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

TOTAL_HEADER = "X-Total-Count"


@dataclass(frozen=True)
class Page:
    limit: int
    offset: int


def page(default: int = 25, maximum: int = 100):
    """A FastAPI dependency: `page: Page = Depends(page(50, 200))` gives `limit` and `offset` query parameters with those bounds."""

    def dependency(
        limit: int = Query(default, ge=1, le=maximum, description="How many to return."),
        offset: int = Query(0, ge=0, description="How many to skip."),
    ) -> Page:
        return Page(limit, offset)

    return dependency


async def count(db: AsyncSession, query: Select) -> int:
    """How many rows a query would return without paging."""
    return (await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()


def send_total(response: Response, total: int) -> None:
    response.headers[TOTAL_HEADER] = str(total)


def window(query: Select, p: Page) -> Select:
    return query.offset(p.offset).limit(p.limit)


def meta(p: Page, total: int) -> dict:
    return {"total": total, "limit": p.limit, "offset": p.offset}
