// The renderer downloads URLs it is handed (chunks, anchors, media to analyse). Those come from our API, but if the
// shared secret ever leaked this would be an SSRF primitive into the private network. So: only http(s), never the
// cloud metadata range, and in production only the hosts we expect (RENDERER_ALLOWED_HOSTS, e.g. the R2 endpoint).
const BLOCKED = [/^169\.254\./, /^0\./, /^fd[0-9a-f]{2}:/i, /^fe80:/i, /^metadata\.google\.internal$/i];

export function assertAllowedUrl(raw: string, allowed = process.env.RENDERER_ALLOWED_HOSTS): URL {
  let u: URL;
  try { u = new URL(raw); } catch { throw new Error("invalid url"); }
  if (!["http:", "https:"].includes(u.protocol)) throw new Error("unsupported url scheme");
  const host = u.hostname.replace(/^\[|\]$/g, "").toLowerCase();
  if (BLOCKED.some((re) => re.test(host))) throw new Error("url host is not allowed");
  const list = (allowed ?? "").split(",").map((h) => h.trim().toLowerCase()).filter(Boolean);
  if (list.length && !list.some((h) => (h.startsWith("*.") ? host.endsWith(h.slice(1)) : host === h))) throw new Error("url host is not allowed");
  return u;
}
