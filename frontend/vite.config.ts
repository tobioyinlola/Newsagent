import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { securityHeaders } from "./security-headers.mjs";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Never inline fonts as data: URIs; the CSP only allows font-src 'self'.
  build: { assetsInlineLimit: (file: string) => (/\.woff2?$/.test(file) ? false : undefined) },
  server: { proxy: { "/v1": "http://localhost:8000", "/health": "http://localhost:8000" } },
  preview: { headers: securityHeaders(), proxy: { "/v1": "http://localhost:8000", "/health": "http://localhost:8000" } },
  test: { environment: "jsdom" },
});
