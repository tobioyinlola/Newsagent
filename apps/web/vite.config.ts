import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/v1": "http://localhost:8000", "/health": "http://localhost:8000" } },
  test: { environment: "jsdom" },
});
