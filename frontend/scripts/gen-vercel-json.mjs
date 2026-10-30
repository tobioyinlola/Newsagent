// Writes vercel.json: the single-page-app fallback, the build, and the same security headers the app is tested with.
// Vercel serves static files, so these headers are fixed in the file rather than read from the environment at run time.
// Defaults are wildcards for the hosts staging uses (Railway for the API, Cloudflare R2 for files, LiveKit Cloud for the
// interview room). Once the real domains are known, tighten them: API_ORIGIN=https://api.example.com STORAGE_ORIGIN=... node scripts/gen-vercel-json.mjs
import fs from "node:fs";
import { securityHeaders } from "../security-headers.mjs";

const env = {
  API_ORIGIN: process.env.API_ORIGIN || "https://*.up.railway.app",
  STORAGE_ORIGIN: process.env.STORAGE_ORIGIN || "https://*.r2.cloudflarestorage.com",
  LIVEKIT_ORIGIN: process.env.LIVEKIT_ORIGIN || "wss://*.livekit.cloud",
  PRESENTER_IMG_ORIGINS: process.env.PRESENTER_IMG_ORIGINS,
};
// The API lives on Railway. Vercel forwards the site's /v1/... calls there, so the browser only ever talks to this site (no CORS,
// and it works even if VITE_API_URL was never set at build time). Change API_TARGET if the backend moves.
const API_TARGET = process.env.API_TARGET || "https://backend-production-73a97.up.railway.app";
// Link-preview crawlers (WhatsApp, LinkedIn, X, Facebook, Slack, search bots) get a small page with the story's headline, summary and
// cover picture from the API, because the app itself has none of that in its HTML. People always get the app.
const CRAWLERS = "facebookexternalhit|Facebot|WhatsApp|LinkedInBot|Twitterbot|Slackbot|TelegramBot|Discordbot|SkypeUriPreview|Pinterest|redditbot|Googlebot|bingbot|Applebot";
const headers = Object.entries(securityHeaders(env)).map(([key, value]) => ({ key, value }));
const config = {
  $schema: "https://openapi.vercel.sh/vercel.json",
  installCommand: "pnpm install --frozen-lockfile",
  buildCommand: "pnpm build",
  outputDirectory: "dist",
  rewrites: [
    { source: "/v1/(.*)", destination: `${API_TARGET}/v1/$1` },
    {
      source: "/latest-stories/:slug",
      has: [{ type: "header", key: "user-agent", value: `(?i).*(${CRAWLERS}).*` }],
      destination: `${API_TARGET}/v1/public/stories/:slug/preview`,
    },
    { source: "/(.*)", destination: "/index.html" },
  ],
  headers: [
    { source: "/(.*)", headers: [...headers, { key: "Cache-Control", value: "no-cache" }] },
    { source: "/assets/(.*)", headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }] },
  ],
};
fs.writeFileSync("vercel.json", JSON.stringify(config, null, 2) + "\n");
