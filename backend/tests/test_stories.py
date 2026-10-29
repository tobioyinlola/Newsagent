"""Latest Stories: a finished video's page is published automatically, shown to the public without the media contact, and
the owner can take it down."""

from sqlalchemy import select

from app.models import Project, Workspace
from app.pipeline.queue import get_queue
from app.services import stories
from tests.conftest import OWNER
from tests.test_guided_flow import interviewed
from tests.test_live_interview import state


async def finished_story(client):
    pid = await interviewed(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["confirmed_claims"] = [c["text"] for c in script["claim_flags"]]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    assert (await client.post(f"/v1/projects/{pid}/script/approve", json={}, headers=OWNER)).status_code == 200
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    return pid


def test_slugs_are_readable_ascii_and_unique_per_project():
    s = stories.make_slug("Onyeka & Sons Ltd Raises $100 Million — Naïve Café!", "Onyeka", "abcdef123")
    assert s == "onyeka-sons-ltd-raises-100-million-naive-cafe-abcdef"
    assert stories.make_slug("", "", "123456789") == "story-123456"
    long = stories.make_slug("word " * 60, "x", "abcdef123")
    assert len(long) <= 70 + 7 and not long.startswith("-") and long.endswith("-abcdef")


async def test_a_finished_video_is_published_automatically_and_shown_publicly(client, workspace, maker):
    pid = await finished_story(client)
    pub = (await client.get(f"/v1/projects/{pid}/publication", headers=OWNER)).json()
    assert pub["published"] and pub["path"].startswith("/latest-stories/") and pub["slug"].endswith(pid[:6])

    cards = (await client.get("/v1/public/stories")).json()  # no sign-in
    assert [c["slug"] for c in cards] == [pub["slug"]]
    assert cards[0]["title"] and cards[0]["thumbnail_url"] and cards[0]["duration_s"] is not None

    page = (await client.get(f"/v1/public/stories/{pub['slug']}")).json()
    assert page["video_url"] and page["sections"] and page["about"] and page["disclosure"]
    assert "contact" not in page and "email" not in str(page).lower().replace(
        "e-mail", ""
    )  # the media contact is never public


async def test_the_owner_can_take_the_story_down_and_put_it_back(client, workspace):
    pid = await finished_story(client)
    slug = (await client.get(f"/v1/projects/{pid}/publication", headers=OWNER)).json()["slug"]
    down = (await client.delete(f"/v1/projects/{pid}/publication", headers=OWNER)).json()
    assert down["published"] is False and down["slug"] == slug
    assert (await client.get("/v1/public/stories")).json() == []
    assert (await client.get(f"/v1/public/stories/{slug}")).status_code == 404
    again = (await client.post(f"/v1/projects/{pid}/publication", headers=OWNER)).json()
    assert again["published"] and again["slug"] == slug  # the same address as before
    assert (await client.get(f"/v1/public/stories/{slug}")).status_code == 200


async def test_a_suspended_or_sharing_disabled_workspace_is_never_shown(client, workspace, maker):
    pid = await finished_story(client)
    slug = (await client.get(f"/v1/projects/{pid}/publication", headers=OWNER)).json()["slug"]
    async with maker() as s:
        ws = await s.get(Workspace, workspace)
        ws.share_disabled = True
        await s.commit()
    assert (await client.get("/v1/public/stories")).json() == []
    assert (await client.get(f"/v1/public/stories/{slug}")).status_code == 404


async def test_other_workspaces_cannot_change_a_story(client, workspace, maker):
    from app.models import User

    pid = await finished_story(client)
    async with maker() as s:
        ws = Workspace(name="Other")
        s.add(ws)
        await s.flush()
        s.add(User(email="other@example.com", workspace_id=ws.id))
        await s.commit()
    other = {"Authorization": "Bearer dev:other@example.com"}
    for call in (client.get, client.post, client.delete):
        assert (await call(f"/v1/projects/{pid}/publication", headers=other)).status_code == 404
    async with maker() as s:
        assert (await s.execute(select(Project).where(Project.id == pid))).scalar_one().published_at is not None


async def test_a_video_without_a_written_story_is_not_published(client, workspace, maker):
    from tests.helpers import make_final_ready

    pid = await make_final_ready(client)  # the original script-first flow has no press release
    pub = (await client.get(f"/v1/projects/{pid}/publication", headers=OWNER)).json()
    assert pub["published"] is False and pub["slug"] is None
    assert (await client.get("/v1/public/stories")).json() == []
