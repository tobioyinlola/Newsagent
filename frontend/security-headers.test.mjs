import { describe, expect, it } from "vitest";
import { securityHeaders } from "./security-headers.mjs";

const csp = (opts) => Object.fromEntries(securityHeaders({ API_ORIGIN: "https://api.example.com" }, opts)["Content-Security-Policy"].split("; ").map((d) => [d.split(" ")[0], d.split(" ").slice(1)]));

describe("the security policy", () => {
  it("lets the public site load Google Analytics and report to it, and nothing else new", () => {
    const p = csp({ analytics: true });
    expect(p["script-src"]).toEqual(["'self'", "https://www.googletagmanager.com"]);
    expect(p["connect-src"]).toEqual(expect.arrayContaining(["https://www.google-analytics.com", "https://*.analytics.google.com"]));
    expect(p["img-src"]).toContain("https://www.google-analytics.com");
    expect(p["default-src"]).toEqual(["'self'"]);
    expect(p["object-src"]).toEqual(["'none'"]);
    expect(p["frame-ancestors"]).toEqual(["'none'"]);
  });
  it("keeps the back office strict: no third-party script and no reporting address", () => {
    const p = csp({ analytics: false });
    expect(p["script-src"]).toEqual(["'self'"]);
    expect(JSON.stringify(p)).not.toMatch(/google/);
  });
});
