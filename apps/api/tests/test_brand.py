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


async def test_voices_and_accent_validation(client, workspace):
    v = await client.get("/v1/voices", headers=OWNER)
    assert {x["accent"] for x in v.json()} == set(brand.ALLOWED_VOICE_ACCENTS)
    r = await client.post("/v1/projects", json={"brief_text": "x" * 30, "voice_accent": "martian"}, headers=OWNER)
    assert r.status_code == 422


async def test_import_pins_the_validated_ip_so_dns_rebinding_cannot_swap_it(monkeypatch):
    import socket

    resolutions = []

    def fake_getaddrinfo(host, port, proto=0):
        resolutions.append(host)
        # a rebinding attacker answers differently each time: public first, then loopback
        ip = "93.184.216.34" if len(resolutions) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    seen = {}

    class Capture(httpx.AsyncClient):
        def __init__(self, *a, **k):
            super().__init__(transport=httpx.MockTransport(self.handler), timeout=10)

        @staticmethod
        def handler(req: httpx.Request) -> httpx.Response:
            seen["host"], seen["header"], seen["sni"] = (
                req.url.host,
                req.headers["host"],
                req.extensions.get("sni_hostname"),
            )
            return httpx.Response(200, text="<title>Acme</title>")

    monkeypatch.setattr(brand.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(brand.httpx, "AsyncClient", Capture)
    d = await brand.import_from_website("https://acme.example/")
    assert d["company_name"] == "Acme"
    assert seen == {"host": "93.184.216.34", "header": "acme.example", "sni": "acme.example"}
    assert resolutions == ["acme.example"]  # resolved once; the client never looked the name up again


def test_resolve_refuses_if_any_answer_is_private(monkeypatch):
    import socket

    monkeypatch.setattr(
        brand.socket,
        "getaddrinfo",
        lambda h, p, proto=0: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", p)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", p)),
        ],
    )
    with pytest.raises(brand.UnsafeUrl):
        brand.resolve_public("https://mixed.example/")


def test_pin_to_ip_handles_ports_and_ipv6():
    url, headers, ext = brand.pin_to_ip("https://acme.example:8443/a?b=1", "93.184.216.34")
    assert (
        url == "https://93.184.216.34:8443/a?b=1"
        and headers["Host"] == "acme.example:8443"
        and ext["sni_hostname"] == "acme.example"
    )
    assert brand.pin_to_ip("http://x.example/", "2606:2800:220:1::1")[0] == "http://[2606:2800:220:1::1]/"
