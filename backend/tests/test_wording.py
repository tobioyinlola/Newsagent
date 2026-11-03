"""Operators can correct a name across a finished video (story, presenter lines, ticker, lower thirds) and re-render it."""

import re

from sqlalchemy import select

from app.models import ScriptVersion
from app.pipeline.queue import get_queue
from tests.conftest import OPS, OWNER
from tests.test_live_interview import state
from tests.test_stories import finished_story


def _word(headline: str) -> str:
    return next(w for w in re.findall(r"[A-Za-z]{4,}", headline))


async def test_an_operator_can_correct_a_name_and_make_the_video_again(client, workspace, maker):
    pid = await finished_story(client)
    before = (await client.get(f"/v1/projects/{pid}/story", headers=OWNER)).json()
    word = _word(before["headline"])
    url = f"/v1/admin/projects/{pid}/wording"

    # customers can't, and a preview changes nothing
    assert (await client.post(url, json={"find": word, "replace": "Womenovate"}, headers=OWNER)).status_code in (
        401,
        403,
    )
    preview = await client.post(url, json={"find": word, "replace": "Womenovate"}, headers=OPS)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["applied"] is False and body["total"] > 0 and body["found"]["story"] > 0
    assert "recorded answers are never changed" in body["note"]
    assert (await client.get(f"/v1/projects/{pid}/story", headers=OWNER)).json()["headline"] == before["headline"]

    # nothing to change, or nothing new: refused
    assert (await client.post(url, json={"find": word, "replace": word}, headers=OPS)).status_code == 422
    assert (await client.post(url, json={"find": "zzzz-not-there", "replace": "Womenovate"}, headers=OPS)).json()[
        "total"
    ] == 0
    assert (
        await client.post(url, json={"find": word, "replace": "X", "rerender": True}, headers=OPS)
    ).status_code == 422

    # apply and make the video again
    done = await client.post(
        url, json={"find": word, "replace": "Womenovate", "apply": True, "rerender": True}, headers=OPS
    )
    assert done.status_code == 200, done.text
    assert done.json()["applied"] is True and done.json()["rerendering"] is True and done.json()["version"] >= 2
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    after = (await client.get(f"/v1/projects/{pid}/story", headers=OWNER)).json()
    assert "Womenovate" in after["headline"] and word not in after["headline"].replace("Womenovate", "")
    page = (
        await client.get(
            f"/v1/public/stories/{(await client.get(f'/v1/projects/{pid}/publication', headers=OWNER)).json()['slug']}"
        )
    ).json()
    assert "Womenovate" in page["title"]  # the page address stays the same, so shared links keep working
    async with maker() as s:
        latest = (
            (
                await s.execute(
                    select(ScriptVersion).where(ScriptVersion.project_id == pid).order_by(ScriptVersion.version.desc())
                )
            )
            .scalars()
            .first()
        )
        assert latest.approved and latest.story and "Womenovate" in latest.story["headline"]
        assert (
            "Womenovate" in " ".join(x["text"] for x in latest.segments)
            or done.json()["found"].get("presenter_lines", 0) == 0
        )
