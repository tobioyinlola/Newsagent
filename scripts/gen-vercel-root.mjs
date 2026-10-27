// Writes the repo-root vercel.json: ONE Vercel project that serves the customer app (frontend/) and the back office (frontend/admin/) as
// two separate SITES. Which one a visitor gets depends on the web address they used, not on a path, so the two never share an
// origin (and so never share a sign-in token). Each site keeps its own Content-Security-Policy.
//   node scripts/gen-vercel-root.mjs
// Add both addresses under the project's Settings > Domains. To use your own domains later, change ADMIN_HOST / APP_HOST here
// (or pass them as environment variables), run this again, and commit the result.
import fs from "node:fs";
import { securityHeaders as webHeaders } from "../frontend/security-headers.mjs";
import { securityHeaders as adminHeaders } from "../frontend/admin/security-headers.mjs";

const ADMIN_HOST = process.env.ADMIN_HOST || "cover-founder-admin.vercel.app";
const env = {
  API_ORIGIN: process.env.API_ORIGIN || "https://*.up.railway.app",
  STORAGE_ORIGIN: process.env.STORAGE_ORIGIN || "https://*.r2.cloudflarestorage.com",
  LIVEKIT_ORIGIN: process.env.LIVEKIT_ORIGIN || "wss://*.livekit.cloud",
};
const list = (h) => Object.entries(h).map(([key, value]) => ({ key, value }));
const onAdmin = [{ type: "host", value: ADMIN_HOST.replace(/\./g, "\\.") }];

const config = {
  $schema: "https://openapi.vercel.sh/vercel.json",
  services: {
    admin: { root: "frontend/admin", framework: "vite", buildCommand: "pnpm build" },
    frontend: { root: "frontend", framework: "vite", buildCommand: "pnpm build" },
  },
  rewrites: [
    { source: "/(.*)", has: onAdmin, destination: { service: "admin" } },
    { source: "/(.*)", destination: { service: "frontend" } },
  ],
  headers: [
    { source: "/(.*)", has: onAdmin, headers: [...list(adminHeaders(env)), { key: "Cache-Control", value: "no-cache" }] },
    { source: "/(.*)", missing: onAdmin, headers: [...list(webHeaders(env)), { key: "Cache-Control", value: "no-cache" }] },
    { source: "/assets/(.*)", headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }] },
  ],
};
fs.writeFileSync("vercel.json", JSON.stringify(config, null, 2) + "\n");
