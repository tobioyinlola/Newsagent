"""Every list is paged the same way, and none can be asked for an unbounded number of rows."""

import pytest
from fastapi import Depends, FastAPI, Response
from httpx import ASGITransport, AsyncClient

from app.services import paging


def _app():
    app = FastAPI()

    @app.get("/items")
    async def items(response: Response, p: paging.Page = Depends(paging.page(10, 25))):
        paging.send_total(response, 100)
        return {"limit": p.limit, "offset": p.offset, **paging.meta(p, 100)}

    return app


@pytest.fixture
async def c():
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as client:
        yield client


async def test_defaults_and_total_header(c):
    r = await c.get("/items")
    assert r.json() == {"limit": 10, "offset": 0, "total": 100}
    assert r.headers["x-total-count"] == "100"


async def test_limit_and_offset_are_taken_and_bounded(c):
    assert (await c.get("/items?limit=25&offset=50")).json()["limit"] == 25
    for bad in ("limit=26", "limit=0", "limit=-1", "offset=-1", "limit=abc"):
        assert (await c.get(f"/items?{bad}")).status_code == 422
