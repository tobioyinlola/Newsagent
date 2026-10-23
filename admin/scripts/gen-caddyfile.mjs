import fs from "node:fs";
import { securityHeaders } from "../security-headers.mjs";

const h = Object.entries(securityHeaders())
  .map(([k, v]) => `    ${k} "${v.replace(/"/g, '\\"')}"`)
  .join("\n");
fs.writeFileSync(
  "Caddyfile",
  `:{$PORT:8080} {
  root * /srv
  encode gzip
  header {
${h}
    Strict-Transport-Security "max-age=31536000; includeSubDomains"
    # index.html must always be fresh so a deploy takes effect; hashed assets can be cached forever
    -Server
  }
  @assets path /assets/*
  header @assets Cache-Control "public, max-age=31536000, immutable"
  @html not path /assets/*
  header @html Cache-Control "no-cache"
  try_files {path} /index.html
  file_server
}
`,
);
console.log("wrote Caddyfile");
