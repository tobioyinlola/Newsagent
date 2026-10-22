"""Brand kit helpers: WCAG contrast checks, accent alternatives, and SSRF-safe website import."""

import colorsys
import ipaddress
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
DARK_TEXT, LIGHT_TEXT = "#111111", "#FFFFFF"
ALLOWED_VOICE_ACCENTS = ["nigerian", "ghanaian", "kenyan", "south_african", "british", "american"]


def _rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(r: float, g: float, b: float) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(round(max(0, min(1, c)) * 255) for c in (r, g, b)))


def luminance(h: str) -> float:
    def f(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (f(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def check_text_contrast(bg: str, text: str, minimum: float = 4.5) -> dict:
    ratio = contrast_ratio(bg, text)
    result: dict = {"background": bg, "text": text, "ratio": ratio, "passes": ratio >= minimum}
    if not result["passes"]:
        result["suggested_background"] = suggest_background(bg, text, minimum)
    return result


def suggest_background(bg: str, text: str, minimum: float = 4.5) -> str:
    """Nudge lightness away from the text colour until the contrast passes."""
    h, light, s = colorsys.rgb_to_hls(*_rgb(bg))
    step = -0.02 if luminance(text) > 0.5 else 0.02  # light text -> darken bg; dark text -> lighten bg
    for _ in range(50):
        light = max(0.0, min(1.0, light + step))
        cand = _hex(*colorsys.hls_to_rgb(h, light, s))
        if contrast_ratio(cand, text) >= minimum:
            return cand
    return cand


def brand_contrast_report(primary: str, accent: str) -> list[dict]:
    """The renderer puts light text on primary and dark text on accent; check exactly those pairs."""
    return [check_text_contrast(primary, LIGHT_TEXT), check_text_contrast(accent, DARK_TEXT)]


def accent_alternatives(accent: str) -> list[str]:
    """The extracted colour plus 3 alternatives (BR-4): complementary, analogous, and a lighter tint."""
    h, light, s = colorsys.rgb_to_hls(*_rgb(accent))
    alts = [
        _hex(*colorsys.hls_to_rgb((h + 0.5) % 1, light, s)),
        _hex(*colorsys.hls_to_rgb((h + 0.08) % 1, light, s)),
        _hex(*colorsys.hls_to_rgb(h, min(0.8, light + 0.15), s)),
    ]
    return [accent.upper(), *alts]


# ---------- website import ----------


class UnsafeUrl(ValueError):
    pass


def resolve_public(url: str) -> str:
    """Resolve the URL's host ONCE and return an IP address, refusing anything that isn't public internet."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrl("Only http(s) URLs are allowed")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UnsafeUrl("Could not resolve that website") from e
    ips = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not ips or any(not ip.is_global for ip in ips):  # one private answer is enough to refuse (rebinding sets traps)
        raise UnsafeUrl("That address is not allowed")
    return str(ips[0])


def assert_public_url(url: str) -> None:
    resolve_public(url)


def pin_to_ip(url: str, ip: str) -> tuple[str, dict[str, str], dict]:
    """Rewrite the URL to connect to the already-validated IP, keeping the original Host header and TLS server name.
    Without this the HTTP client resolves the name again and a DNS-rebinding attacker can swap in 127.0.0.1."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    netloc_ip = f"[{ip}]" if ":" in ip else ip
    port = f":{parsed.port}" if parsed.port else ""
    pinned = parsed._replace(netloc=f"{netloc_ip}{port}").geturl()
    return pinned, {"Host": f"{host}{port}"}, {"sni_hostname": host}


class _Meta(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.meta: dict[str, str] = {}
        self.icons: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = a.get("property") or a.get("name")
            if key:
                self.meta[key.lower()] = a.get("content", "")
        elif tag == "link" and "icon" in a.get("rel", "").lower():
            self.icons.append(a.get("href", ""))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


async def import_from_website(url: str, client: httpx.AsyncClient | None = None, check_url=assert_public_url) -> dict:
    """Return a DRAFT kit; the user confirms or edits every field (BR-1, BR-2). Never saved automatically."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=10)
    try:
        current = url
        for _ in range(4):  # manual redirects so each hop is re-validated
            headers = {"User-Agent": "NewsagentBrandImport/1.0"}
            ext: dict = {}
            target = current
            if own:  # production: validate once, then connect to exactly that IP
                target, host_header, ext = pin_to_ip(current, resolve_public(current))
                headers.update(host_header)
            else:
                check_url(current)
            r = await client.get(target, follow_redirects=False, headers=headers, extensions=ext)
            if r.is_redirect:
                current = urljoin(current, r.headers["location"])
                continue
            break
        else:
            raise UnsafeUrl("Too many redirects")
        r.raise_for_status()
        html = r.text[:1_000_000]
    finally:
        if own:
            await client.aclose()

    p = _Meta()
    p.feed(html)
    colors: dict[str, int] = {}
    for m in re.findall(r"#[0-9a-fA-F]{6}\b", html):
        c = m.upper()
        if c not in {"#FFFFFF", "#000000"}:
            colors[c] = colors.get(c, 0) + 1
    ranked = [c for c, _ in sorted(colors.items(), key=lambda kv: -kv[1])]
    theme = p.meta.get("theme-color", "")
    primary = theme.upper() if HEX.match(theme) else (ranked[0] if ranked else None)
    accent = next((c for c in ranked if c != primary), None)
    logo = p.meta.get("og:image") or (p.icons[0] if p.icons else None)
    return {
        "company_name": (p.meta.get("og:site_name") or p.title.strip() or None),
        "primary_color": primary,
        "accent_color": accent,
        "logo_url": urljoin(current, logo) if logo else None,
        "source_url": url,
        "confirmed": False,
    }
