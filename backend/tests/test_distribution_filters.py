"""Outlets can be browsed by topic and place, by visitors who are not signed in and by customers."""

from app.routes.distribution import LOCATIONS, NAMES, OUTLETS, REGION_OF, TOPICS
from app.services import distribution_catalog as catalog_service
from tests.conftest import OWNER


def test_every_outlet_has_a_valid_topic_and_place():
    assert len(OUTLETS) == len(NAMES) == 53
    for o in OUTLETS.values():
        assert o["topic"] in TOPICS, o["name"]
        assert o["region"] in LOCATIONS, o["name"]
        if o["country"] is None:  # the crypto channels cover Africa as a whole
            assert o["region"] == "Africa"
        else:
            assert o["country"] in REGION_OF and o["region"] == REGION_OF[o["country"]], o["name"]


def test_known_outlets_are_filed_where_the_owner_expects():
    by = {o["name"]: o for o in OUTLETS.values()}
    assert (by["Techpoint Africa"]["topic"], by["Techpoint Africa"]["country"]) == ("Technology", "Nigeria")
    assert (by["Naijaloaded"]["topic"], by["Naijaloaded"]["region"]) == ("Gossip Blogs", "Africa")
    assert (by["Daily Nation"]["country"], by["Daily Nation"]["topic"]) == ("Kenya", "General News")
    assert (by["Benzinga"]["country"], by["Benzinga"]["region"]) == ("United States", "North America")
    assert by["The Globe and Mail"]["country"] == "Canada"
    assert by["CoinSpeaks"]["topic"] == "Technology" and by["CoinSpeaks"]["country"] is None


def test_outlet_ids_did_not_change():
    assert OUTLETS["1"]["name"] == "Empire Magazine Africa" and OUTLETS["53"]["name"] == "Daily Nation"


async def test_a_visitor_can_browse_outlets_without_signing_in(client, maker):
    r = await client.get("/v1/public/distribution/outlets")
    assert r.status_code == 200
    body = r.json()
    assert "max-age" in r.headers["cache-control"]
    assert set(body["filters"]["topics"]) == set(TOPICS)
    assert {x["region"] for x in body["filters"]["locations"]} == set(LOCATIONS)
    assert body["outlets"], "priced outlets are listed"
    for o in body["outlets"]:
        assert set(o) == {"id", "name", "topic", "category", "region", "country", "credits"}  # nothing internal
        assert float(o["credits"]) > 0  # free channels stay hidden
    shown_countries = {o["country"] for o in body["outlets"]}
    assert set(body["coming_soon"]) == {
        c for c in REGION_OF if c not in shown_countries
    }  # exactly the places with nothing to show
    assert {"Ghana", "Uganda", "United Kingdom"} <= set(body["coming_soon"])


async def test_the_signed_in_list_has_the_same_tags_and_filters(client, workspace):
    r = (await client.get("/v1/distribution/outlets", headers=OWNER)).json()
    first = r["outlets"][0]
    assert {"topic", "country", "region"} <= set(first)
    assert r["filters"] == (await client.get("/v1/public/distribution/outlets")).json()["filters"]
    assert r["quote_version"]  # the price check on submit is unchanged


def test_prices_shown_to_visitors_are_the_real_catalogue_prices():
    assert not catalog_service.is_hidden({"credits": "42"})
    assert catalog_service.is_hidden({"credits": "0"}) is True
