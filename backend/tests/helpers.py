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


# ---------- founder interview ----------
async def make_awaiting_founder(client, questions=None):
    """Project through anchor + question clips, with the founder interview enabled."""
    r = await client.post("/v1/projects", json=BRIEF, headers=OWNER)
    pid = r.json()["id"]
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [
        {"kind": "intro", "text": "Tonight we feature Acme, a farm marketplace."},
        {"kind": "body", "text": "Acme connects farmers to buyers."},
        {"kind": "outro", "text": "That was Acme. Back to you."},
    ]
    if questions:
        body["interview_questions"] = questions
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    r = await client.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": True}, headers=OWNER)
    assert r.status_code == 200, r.text
    await get_queue().drain()
    return pid


async def invite(client, pid, email="founder@startup.example.com", name="Ada Obi", title="CEO, Acme"):
    r = await client.post(
        f"/v1/projects/{pid}/interview",
        json={"founder_name": name, "founder_title": title, "founder_email": email},
        headers=OWNER,
    )
    assert r.status_code == 200, r.text
    return r.json()["url"].rsplit("/i/", 1)[1]


def api_path(url: str) -> str:
    return url.replace("http://localhost:8000", "")


async def upload_chunks(client, token, take_id, indexes, size=1000):
    r = await client.post(f"/v1/interview/{token}/takes/{take_id}/chunk-urls", json={"indexes": indexes})
    assert r.status_code == 200, r.text
    for i, url in r.json()["urls"].items():
        assert (await client.put(api_path(url), content=b"x" * size)).status_code == 200
        c = await client.post(f"/v1/interview/{token}/takes/{take_id}/chunks/{i}/confirm")
        assert c.status_code == 200, c.text
    return c.json()


async def record(client, token, question=0, chunks=3, kind="video", mime="video/webm;codecs=vp9,opus", consent=True):
    if consent:
        await client.post(f"/v1/interview/{token}/consent")
    r = await client.post(f"/v1/interview/{token}/takes", json={"question_index": question, "kind": kind, "mime": mime})
    assert r.status_code == 200, r.text
    take_id = r.json()["id"]
    await upload_chunks(client, token, take_id, list(range(chunks)))
    c = await client.post(f"/v1/interview/{token}/takes/{take_id}/complete", json={"chunk_count": chunks})
    assert c.status_code == 200, c.text
    await get_queue().drain()
    return take_id
