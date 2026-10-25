// One source of truth for the web app's security headers. Used by `vite preview` (so tests enforce it) and rendered
// into the production Caddyfile by scripts/gen-caddyfile.mjs. API_ORIGIN / STORAGE_ORIGIN are where the browser may
// connect: the API, and the object storage that presigned upload/download URLs point at.
export function securityHeaders(env = process.env) {
  const api = env.API_ORIGIN || "http://localhost:8000";
  const origins = [...new Set([api, env.STORAGE_ORIGIN || api])].join(" ");
  // the presenter picker shows the avatar vendor's public preview pictures
  const presenterImages = env.PRESENTER_IMG_ORIGINS || "https://resource2.heygen.ai https://files2.heygen.ai";
  const csp = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'", // React inline styles (the app sets colours/widths via style=)
    `img-src 'self' data: blob: ${origins} ${presenterImages}`,
    `media-src 'self' blob: ${origins}`,
    `connect-src 'self' ${origins}`,
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
  return {
    "Content-Security-Policy": csp,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    // The founder page needs the camera and microphone, and nothing else needs anything.
    "Permissions-Policy": "camera=(self), microphone=(self), geolocation=()",
  };
}
