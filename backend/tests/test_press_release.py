"""Distribution without a video: a press release written from the details, or read from a file the business already has."""

import io
import zipfile

from tests.conftest import OWNER

URL = "/v1/distribution/press-release"
DETAILS = {
    "kind": "funding_round",
    "details": "Acme Farms raised a seed round to help smallholder farmers in Ghana sell produce to verified buyers on their phones.",
    "first_name": "Ada",
    "last_name": "Obi",
    "role": "CEO",
    "company": "ACME FARMS",
    "city": "LAGOS",
    "country": "NIGERIA",
    "website": "acmefarms.example.com",
}


def docx(paragraphs: list[str], extra: bytes = b"") -> bytes:
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<?xml version="1.0"?>{extra.decode()}<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("word/document.xml", xml)
    return out.getvalue()


def pdf(text: str) -> bytes:
    """A one-page PDF with a line of text, written by hand so no extra tool is needed."""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        None,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    stream = f"BT /F1 12 Tf 72 700 Td ({text}) Tj ET".encode()
    objs[3] = b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, xref)


async def test_a_press_release_is_written_from_the_details(client, workspace):
    r = await client.post(URL, json=DETAILS, headers=OWNER)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["headline"] and out["announcement"].strip() and out["kind"] == "Funding round"
    assert out["announcement"].startswith("LAGOS, NIGERIA — ")  # the dateline comes from the city and country given
    assert "About ACME FARMS" in out["announcement"]


async def test_the_details_are_checked_before_anything_is_written(client, workspace):
    assert (await client.post(URL, json=DETAILS)).status_code in (401, 403)
    assert (await client.post(URL, json={**DETAILS, "details": "too short"}, headers=OWNER)).status_code == 422
    assert (await client.post(URL, json={**DETAILS, "details": "word " * 251}, headers=OWNER)).status_code == 422
    for missing in ("first_name", "last_name", "role", "company", "city", "country"):
        assert (await client.post(URL, json={**DETAILS, missing: ""}, headers=OWNER)).status_code == 422, missing


async def test_an_uploaded_press_release_is_read_and_split_into_headline_and_body(client, workspace):
    text = "FOR IMMEDIATE RELEASE\n\nAcme Farms raises a seed round\n\nLAGOS, NIGERIA — Acme Farms today announced a seed round.\n\nIt will open in Kumasi."
    for name in ("release.txt", "release.md"):
        r = await client.post(f"{URL}/read?filename={name}", content=text.encode(), headers=OWNER)
        assert r.status_code == 200, r.text
        assert r.json()["headline"] == "Acme Farms raises a seed round"
        assert r.json()["announcement"].startswith("LAGOS, NIGERIA") and "Kumasi" in r.json()["announcement"]
    word = docx(["Acme Farms raises a seed round", "Acme Farms today announced a seed round to open in Kumasi."])
    r = await client.post(f"{URL}/read?filename=release.DOCX", content=word, headers=OWNER)
    assert r.status_code == 200, r.text
    assert r.json()["headline"] == "Acme Farms raises a seed round" and "Kumasi" in r.json()["announcement"]
    r = await client.post(
        f"{URL}/read?filename=release.pdf",
        content=pdf("Acme Farms raises a seed round and plans to open in Kumasi"),
        headers=OWNER,
    )
    assert r.status_code == 200, r.text
    assert "Kumasi" in r.json()["announcement"] + r.json()["headline"]


async def test_files_that_cannot_be_read_are_refused_with_a_plain_reason(client, workspace):
    async def read(name, data):
        return await client.post(f"{URL}/read?filename={name}", content=data, headers=OWNER)

    assert (await read("release.exe", b"MZ....")).status_code == 422  # not a supported type
    assert (await read("release.txt", b"")).status_code == 422  # empty
    assert (await read("release.txt", b"x" * 5)).status_code == 422  # no real text
    assert (await read("release.docx", b"not a zip file at all")).status_code == 422
    assert (await read("release.pdf", b"not a pdf")).status_code == 422
    evil = docx(["Hello there, this is a long enough press release body."], extra=b'<!DOCTYPE x [<!ENTITY a "aaaa">]>')
    assert (await read("release.docx", evil)).status_code == 422  # entity tricks are refused
    assert (await read("release.txt", b"y" * (2 * 1024 * 1024 + 1))).status_code == 413
    assert (
        await client.post(f"{URL}/read?filename=release.txt", content=b"A headline\n\nSome body text here.")
    ).status_code in (401, 403)
