"""The owner can change the press release (subject, summary line, body) while reviewing the story, until they approve."""

from tests.conftest import OWNER
from tests.test_guided_flow import interviewed


async def test_the_owner_can_edit_the_press_release_before_approving(client, workspace):
    pid = await interviewed(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)  # the story is written here
    before = (await client.get(f"/v1/projects/{pid}/story", headers=OWNER)).json()
    social = before["social"]

    body = {
        "headline": "  My   own   subject ",
        "dek": "My own summary.",
        "paragraphs": ["First   paragraph.", "", "Second paragraph."],
    }
    r = await client.put(f"/v1/projects/{pid}/story", json=body, headers=OWNER)
    assert r.status_code == 200, r.text
    after = (await client.get(f"/v1/projects/{pid}/story", headers=OWNER)).json()
    assert after["headline"] == "My own subject" and after["dek"] == "My own summary."
    assert [p for s in after["sections"] for p in s["paragraphs"]] == ["First paragraph.", "Second paragraph."]
    assert after["social"] == social  # the social post is not touched
    assert after.get("about") == before.get("about")

    # nothing to say, or too much, is refused
    assert (
        await client.put(f"/v1/projects/{pid}/story", json={**body, "headline": " "}, headers=OWNER)
    ).status_code == 422
    assert (
        await client.put(f"/v1/projects/{pid}/story", json={**body, "paragraphs": [" ", ""]}, headers=OWNER)
    ).status_code == 422
    assert (
        await client.put(f"/v1/projects/{pid}/story", json={**body, "paragraphs": ["x" * 3001]}, headers=OWNER)
    ).status_code == 422

    # approving locks it
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    payload = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    payload["confirmed_claims"] = [c["text"] for c in script["claim_flags"]]
    await client.put(f"/v1/projects/{pid}/script", json=payload, headers=OWNER)
    assert (await client.post(f"/v1/projects/{pid}/script/approve", json={}, headers=OWNER)).status_code == 200
    assert (await client.put(f"/v1/projects/{pid}/story", json=body, headers=OWNER)).status_code == 409
    assert (await client.get(f"/v1/projects/{pid}/story", headers=OWNER)).json()["headline"] == "My own subject"


async def test_nobody_else_can_edit_a_press_release(client, workspace):
    pid = await interviewed(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)  # the story is written here
    body = {"headline": "Not yours", "dek": "", "paragraphs": ["Nope."]}
    assert (await client.put(f"/v1/projects/{pid}/story", json=body)).status_code in (401, 403)
    assert (
        await client.put(
            f"/v1/projects/{pid}/story", json=body, headers={"Authorization": "Bearer dev:stranger@example.com"}
        )
    ).status_code in (401, 403, 404)
