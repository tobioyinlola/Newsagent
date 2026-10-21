from app.pipeline.queue import get_queue
from tests.conftest import OWNER

BRIEF = {"brief_text": "Acme helps farmers sell produce online across Nigeria and Ghana."}


async def make_final_ready(client, brief=BRIEF, segments=None):
    r = await client.post("/v1/projects", json=brief, headers=OWNER)
    pid = r.json()["id"]
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = segments or [{"kind": "intro", "text": "Tonight we feature Acme, a farm marketplace."}]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    await get_queue().drain()
    return pid
