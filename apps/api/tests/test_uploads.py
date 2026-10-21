import pytest

from app.integrations import registry
from app.integrations.malware.mock import EICAR, MockScanner
from tests.conftest import OWNER
from tests.test_brand import KIT

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'


async def upload(client, data, kind="logo_light", content_type="image/png", declared=None, headers=OWNER):
    r = await client.post(
        "/v1/brand-kit/uploads",
        json={"kind": kind, "content_type": content_type, "size_bytes": declared or len(data)},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    key = r.json()["key"]
    put = await client.put(r.json()["upload_url"].replace("http://localhost:8000", ""), content=data)
    assert put.status_code == 200
    return key


async def confirm(client, key, headers=OWNER):
    return await client.post("/v1/brand-kit/uploads/confirm", json={"key": key}, headers=headers)


async def test_clean_png_confirms_and_lists(client, workspace):
    key = await upload(client, PNG)
    r = await confirm(client, key)
    assert r.status_code == 200 and r.json()["kind"] == "logo_light"
    assets = (await client.get("/v1/brand-kit/assets", headers=OWNER)).json()
    assert [a["key"] for a in assets] == [key] and assets[0]["url"]


@pytest.mark.parametrize(
    "kind,ctype,data",
    [
        ("logo_light", "image/png", b"GIF89a not a png"),  # wrong magic bytes
        ("logo_light", "image/svg+xml", SVG.replace(b"<rect", b"<script>alert(1)</script><rect")),
        ("logo_light", "image/svg+xml", SVG.replace(b"<rect", b'<rect onload="x()"')),
        ("logo_light", "image/svg+xml", SVG.replace(b"<rect", b'<image href="https://evil.example/x.png"/><rect')),
        ("guide_pdf", "application/pdf", b"%PDF-1.4\n/JavaScript (app.alert(1))"),
        ("guide_pdf", "application/pdf", b"MZ\x90 not a pdf"),
        ("product_image", "image/jpeg", PNG),
    ],
)
async def test_invalid_or_active_content_rejected_and_deleted(client, workspace, kind, ctype, data):
    key = await upload(client, data, kind, ctype)
    assert (await confirm(client, key)).status_code == 422
    assert await registry.get_storage().exists(key) is False
    assert (await client.get("/v1/brand-kit/assets", headers=OWNER)).json() == []


async def test_malware_blocked_even_when_type_is_valid(client, workspace):
    key = await upload(client, PNG + EICAR)
    r = await confirm(client, key)
    assert r.status_code == 422 and "security scan" in r.json()["detail"]
    assert await registry.get_storage().exists(key) is False


async def test_scanner_outage_fails_closed(client, workspace):
    class Down(MockScanner):
        async def scan(self, data):
            raise ConnectionError("clamd down")

    registry.override(scanner=Down())
    key = await upload(client, PNG)
    assert (await confirm(client, key)).status_code == 503
    assert (await client.get("/v1/brand-kit/assets", headers=OWNER)).json() == []  # never marked clean
    registry.override(scanner=MockScanner())
    assert (await confirm(client, key)).status_code == 200  # retry works


async def test_declared_size_lies_are_caught_by_real_size(client, workspace):
    key = await upload(client, PNG + b"\x00" * (3 * 1024 * 1024), declared=1000)  # says 1 KB, is 3 MB
    assert (await confirm(client, key)).status_code == 422


async def test_declared_limits_enforced_up_front(client, workspace):
    for body in (
        {"kind": "logo_light", "content_type": "image/gif", "size_bytes": 10},
        {"kind": "logo_light", "content_type": "image/png", "size_bytes": 3_000_000},
        {"kind": "guide_pdf", "content_type": "application/pdf", "size_bytes": 11 * 1024 * 1024},
        {"kind": "product_image", "content_type": "image/svg+xml", "size_bytes": 10},
        {"kind": "weird", "content_type": "image/png", "size_bytes": 10},
    ):
        assert (await client.post("/v1/brand-kit/uploads", json=body, headers=OWNER)).status_code == 422


async def test_other_workspace_cannot_confirm_or_use_key(client, workspace, maker):
    from app.models import User, Workspace

    key = await upload(client, PNG)
    async with maker() as s:
        ws = Workspace(name="Other")
        s.add(ws)
        await s.flush()
        s.add(User(email="other@example.com", workspace_id=ws.id))
        await s.commit()
    other = {"Authorization": "Bearer dev:other@example.com"}
    assert (await confirm(client, key, headers=other)).status_code == 404
    await confirm(client, key)
    r = await client.put("/v1/brand-kit", json={**KIT, "logo_light_key": key}, headers=other)
    assert r.status_code == 422


async def test_kit_logo_must_be_clean_and_matching_kind(client, workspace):
    pending = await upload(client, PNG)
    assert (
        await client.put("/v1/brand-kit", json={**KIT, "logo_light_key": pending}, headers=OWNER)
    ).status_code == 422
    await confirm(client, pending)
    assert (
        await client.put("/v1/brand-kit", json={**KIT, "logo_light_key": pending}, headers=OWNER)
    ).status_code == 200
    assert (await client.put("/v1/brand-kit", json={**KIT, "logo_dark_key": pending}, headers=OWNER)).status_code == 422


async def test_dev_storage_rejects_path_traversal(client, workspace):
    r = await client.get("/v1/dev-storage/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code in (400, 404)
