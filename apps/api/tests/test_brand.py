import httpx
import pytest

from app.services import brand
from tests.conftest import OWNER

KIT = {
    "primary_color": "#0B3D91",
    "accent_color": "#F5A623",
    "tone": "friendly",
    "fonts": {"heading": "Inter", "body": "Lato"},
    "pronunciation_glossary": {"Oyinlola": "oh-yin-LOH-lah"},
}


def test_contrast_math():
    assert brand.contrast_ratio("#000000", "#FFFFFF") == 21.0
    bad = brand.check_text_contrast("#F5F5A0", "#FFFFFF")
    assert not bad["passes"]
    assert brand.contrast_ratio(bad["suggested_background"], "#FFFFFF") >= 4.5


def test_accent_alternatives_returns_original_plus_three():
    alts = brand.accent_alternatives("#F5A623")
    assert len(alts) == 4 and alts[0] == "#F5A623"


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1/", "http://169.254.169.254/latest", "http://localhost:8000", "ftp://x.com", "http://[::1]/"],
)
def test_import_blocks_private_and_non_http(url):
    with pytest.raises(brand.UnsafeUrl):
        brand.assert_public_url(url)


async def test_import_parses_draft_and_revalidates_redirects():
    html = (
        '<html><head><title>Acme Pay</title><meta name="theme-color" content="#112233">'
        '<meta property="og:image" content="/logo.png"></head><body style="color:#AA5500">'
        '<div style="background:#AA5500"></div></body></html>'
    )
    hops = []

    def handler(req: httpx.Request) -> httpx.Response:
        hops.append(str(req.url))
        if req.url.path == "/":
            return httpx.Response(302, headers={"location": "/home"})
        return httpx.Response(200, text=html)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    checked = []
    d = await brand.import_from_website("https://acme.example/", client, check_url=checked.append)
    assert d["company_name"] == "Acme Pay" and d["primary_color"] == "#112233" and d["accent_color"] == "#AA5500"
    assert d["logo_url"] == "https://acme.example/logo.png" and d["confirmed"] is False
    assert len(checked) == 2  # every hop validated


async def test_import_redirect_to_private_is_blocked():
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "http://169.254.169.254/"}))
    )

    def check(u):  # same rule as production, minus DNS
        if "169.254" in u:
            raise brand.UnsafeUrl("blocked")

    with pytest.raises(brand.UnsafeUrl):
        await brand.import_from_website("https://evil.example/", client, check_url=check)


async def test_brand_kit_versioning_and_report(client, workspace):
    r = await client.put("/v1/brand-kit", json=KIT, headers=OWNER)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1 and len(r.json()["accent_alternatives"]) == 4
    r = await client.put("/v1/brand-kit", json={**KIT, "accent_color": "#00AA66"}, headers=OWNER)
    assert r.json()["version"] == 2
    assert (await client.get("/v1/brand-kit", headers=OWNER)).json()["accent_color"] == "#00AA66"


@pytest.mark.parametrize(
    "patch",
    [
        {"tone": "rude"},
        {"fonts": {"heading": "Comic Sans"}},
        {"logo_light_key": "brand/other-workspace/x.png"},
        {"primary_color": "blue"},
    ],
)
async def test_brand_kit_rejects_bad_input(client, workspace, patch):
    assert (await client.put("/v1/brand-kit", json={**KIT, **patch}, headers=OWNER)).status_code == 422


async def test_logo_upload_validation(client, workspace):
    ok = await client.post(
        "/v1/brand-kit/logo-upload", json={"content_type": "image/png", "size_bytes": 1000}, headers=OWNER
    )
    assert ok.status_code == 200 and ok.json()["key"].startswith("brand/")
    for body in (
        {"content_type": "image/gif", "size_bytes": 10},
        {"content_type": "image/png", "size_bytes": 3_000_000},
        {"content_type": "text/html", "size_bytes": 10},
    ):
        assert (await client.post("/v1/brand-kit/logo-upload", json=body, headers=OWNER)).status_code == 422


async def test_voices_and_accent_validation(client, workspace):
    v = await client.get("/v1/voices", headers=OWNER)
    assert {x["accent"] for x in v.json()} == set(brand.ALLOWED_VOICE_ACCENTS)
    r = await client.post("/v1/projects", json={"brief_text": "x" * 30, "voice_accent": "martian"}, headers=OWNER)
    assert r.status_code == 422
