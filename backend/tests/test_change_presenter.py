"""An operator can make a finished video again with a different presenter (the default one unless a look is named)."""

from app.config import get_settings
from app.integrations import registry
from app.integrations.avatar.mock import MockAvatarProvider
from app.models import Project
from app.pipeline.queue import get_queue
from tests.conftest import OPS, OWNER
from tests.test_live_interview import state
from tests.test_scene_editor import finished_video


class Seeing(MockAvatarProvider):
    def __init__(self):
        super().__init__()
        self.avatars: list[str | None] = []

    async def generate(self, req):
        self.avatars.append(req.avatar_id)
        return await super().generate(req)

    async def submit(self, req):
        self.avatars.append(req.avatar_id)
        return await super().submit(req)


async def test_a_finished_video_is_made_again_with_the_default_presenter(client, workspace, maker, monkeypatch):
    pid, _ = await finished_video(client)
    seen = Seeing()
    registry.override(avatar=seen)
    monkeypatch.setattr(get_settings(), "heygen_default_avatar_id", "the-new-default")
    monkeypatch.setattr(get_settings(), "heygen_featured_presenters", "")
    # the owner cannot do it; an operator can, and only once the video is finished
    assert (await client.post(f"/v1/admin/projects/{pid}/presenter", headers=OWNER, json={})).status_code in (401, 403)
    r = await client.post(f"/v1/admin/projects/{pid}/presenter", headers=OPS, json={})
    assert r.status_code == 200, r.text
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"  # the new video is ready and replaces the old
    async with maker() as s:
        assert (await s.get(Project, pid)).anchor_id == "the-new-default"
    assert seen.avatars and set(seen.avatars) == {"the-new-default"}  # every presenter clip was made with her
    # the same presenter again is refused, not paid for twice
    again = await client.post(f"/v1/admin/projects/{pid}/presenter", headers=OPS, json={})
    assert again.status_code == 409
