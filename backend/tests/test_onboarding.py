"""The first-run questions after sign-up, guided-tour progress, and the answers showing on the back office's customer view."""

import pytest

from tests.conftest import OPS, OWNER


@pytest.fixture
async def fresh(client, workspace, maker):
    """A signed-up customer whose first-run questions are still waiting, as a real sign-up leaves them."""
    from app.models import User
    from app.services import onboarding

    async with maker() as db:
        from sqlalchemy import select

        user = (await db.execute(select(User).where(User.workspace_id == workspace))).scalars().first()
        user.onboarding = onboarding.start_for_new_account()
        await db.commit()
    return workspace


async def test_a_new_account_starts_with_the_questions_waiting_and_options_to_choose_from(client, fresh):
    r = (await client.get("/v1/me/onboarding", headers=OWNER)).json()
    assert r["profile_status"] == "pending" and r["profile_step"] == 0 and r["profile"] == {} and r["tours"] == {}
    assert {o["key"] for o in r["options"]["heard"]} >= {"search", "social", "friend", "other"}
    assert r["options"]["steps"] == ["about_you", "your_business", "your_goals", "how_you_heard"]


async def test_an_account_from_before_the_questions_existed_is_not_started_not_pending(client, workspace):
    r = (await client.get("/v1/me/onboarding", headers=OWNER)).json()
    assert r["profile_status"] == "not_started"


async def test_each_card_saves_its_answers_and_the_rest_are_kept(client, fresh):
    r = await client.put(
        "/v1/me/onboarding/profile",
        json={
            "answers": {"contact_name": "  Ada   Obi ", "role": "founder", "phone": "+234 801 000 0000"},
            "step": 1,
            "status": "in_progress",
        },
        headers=OWNER,
    )
    assert r.status_code == 200
    r = (
        await client.put(
            "/v1/me/onboarding/profile",
            json={"answers": {"company_size": "2-10", "website": "acme.example.com"}, "step": 2},
            headers=OWNER,
        )
    ).json()
    assert r["profile"] == {
        "contact_name": "Ada Obi",
        "role": "founder",
        "phone": "+234 801 000 0000",
        "company_size": "2-10",
        "website": "https://acme.example.com",
    }
    assert r["profile_status"] == "in_progress" and r["profile_step"] == 2


async def test_goals_and_how_they_heard_are_saved_and_anything_unknown_is_dropped(client, fresh):
    r = (
        await client.put(
            "/v1/me/onboarding/profile",
            json={
                "answers": {
                    "goals": ["customers", "investors", "customers", "world-domination"],
                    "heard_from": "social",
                    "heard_detail": "LinkedIn post",
                    "role": "wizard",
                    "extra": "x",
                },
                "status": "done",
                "step": 4,
            },
            headers=OWNER,
        )
    ).json()
    assert r["profile"]["goals"] == ["customers", "investors"]
    assert r["profile"]["heard_from"] == "social" and r["profile"]["heard_detail"] == "LinkedIn post"
    assert r["profile"]["role"] == "" and "extra" not in r["profile"]
    assert r["profile_status"] == "done"


async def test_everything_can_be_skipped_and_nothing_is_saved(client, fresh):
    r = (await client.put("/v1/me/onboarding/profile", json={"status": "skipped"}, headers=OWNER)).json()
    assert r["profile_status"] == "skipped" and r["profile"] == {}


async def test_a_bad_status_is_refused(client, fresh):
    assert (await client.put("/v1/me/onboarding/profile", json={"status": "bogus"}, headers=OWNER)).status_code == 422


async def test_tour_progress_is_remembered_finished_and_can_be_restarted(client, workspace):
    r = (await client.put("/v1/me/tours/welcome", json={"step": 2}, headers=OWNER)).json()
    assert r["tours"]["welcome"]["step"] == 2 and r["tours"]["welcome"]["done"] is False
    r = (await client.put("/v1/me/tours/welcome", json={"step": 5, "done": True}, headers=OWNER)).json()
    assert r["tours"]["welcome"]["done"] is True and "done_at" in r["tours"]["welcome"]
    again = (await client.put("/v1/me/tours/welcome", json={"step": 1}, headers=OWNER)).json()
    assert again["tours"]["welcome"]["done"] is True  # finishing is remembered even when someone replays it
    r = (await client.put("/v1/me/tours/welcome", json={"reset": True}, headers=OWNER)).json()
    assert "welcome" not in r["tours"]


async def test_a_tour_can_be_dismissed_and_odd_tour_names_are_refused(client, workspace):
    r = (await client.put("/v1/me/tours/welcome", json={"step": 0, "dismissed": True}, headers=OWNER)).json()
    assert r["tours"]["welcome"]["dismissed"] is True
    assert (await client.put("/v1/me/tours/Bad Name!", json={"step": 0}, headers=OWNER)).status_code in {404, 422}


async def test_the_team_use_tours_too_but_have_no_business_questions(client, workspace):
    assert (await client.put("/v1/me/tours/admin-overview", json={"step": 1}, headers=OPS)).status_code == 200
    r = (await client.get("/v1/me/onboarding", headers=OPS)).json()
    assert r["tours"]["admin-overview"]["step"] == 1
    assert (
        await client.put("/v1/me/onboarding/profile", json={"answers": {"role": "founder"}}, headers=OPS)
    ).status_code == 403


async def test_what_a_customer_told_us_shows_on_their_page_in_the_back_office(client, fresh):
    await client.put(
        "/v1/me/onboarding/profile",
        json={
            "answers": {"role": "marketing", "heard_from": "friend", "heard_detail": "Tunde told me"},
            "status": "done",
        },
        headers=OWNER,
    )
    detail = (await client.get(f"/v1/admin/customers/{fresh}", headers=OPS)).json()
    assert detail["profile"]["role"] == "marketing" and detail["profile"]["heard_detail"] == "Tunde told me"
    assert detail["profile_status"] == "done"


async def test_signing_up_leaves_the_questions_waiting(client, workspace):
    from tests.test_auth_flow import signup

    s = await signup(client)
    r = await client.get("/v1/me/onboarding", headers={"Authorization": f"Bearer {s['token']}"})
    assert r.json()["profile_status"] == "pending"
