// Writes the repo-root vercel.json: ONE Vercel project, one service (frontend/), one site. The operator back office is part of
// that app and is served under /admin, so there is nothing to route by host. The security headers are the app's own.
//   node scripts/gen-vercel-root.mjs
// Defaults are wildcards for the hosts staging uses (Railway for the API, Cloudflare R2 for files, LiveKit Cloud for the
// interview room). Once the real domains are known, tighten them: API_ORIGIN=https://api.example.com node scripts/gen-vercel-root.mjs
import fs from "node:fs";
import { securityHeaders } from "../frontend/security-headers.mjs";

const env = {
  API_ORIGIN: process.env.API_ORIGIN || "https://*.up.railway.app",
  STORAGE_ORIGIN: process.env.STORAGE_ORIGIN || "https://*.r2.cloudflarestorage.com",
  LIVEKIT_ORIGIN: process.env.LIVEKIT_ORIGIN || "wss://*.livekit.cloud",
};
const headers = Object.entries(securityHeaders(env)).map(([key, value]) => ({ key, value }));
const config = {
  $schema: "https://openapi.vercel.sh/vercel.json",
  services: { frontend: { root: "frontend", framework: "vite", buildCommand: "pnpm build" } },
  rewrites: [{ source: "/(.*)", destination: { service: "frontend" } }],
  headers: [
    { source: "/(.*)", headers: [...headers, { key: "Cache-Control", value: "no-cache" }] },
    { source: "/assets/(.*)", headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }] },
  ],
};
fs.writeFileSync("vercel.json", JSON.stringify(config, null, 2) + "\n");
