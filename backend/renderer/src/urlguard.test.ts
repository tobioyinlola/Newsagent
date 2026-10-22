import { describe, expect, it } from "vitest";
import { assertAllowedUrl } from "./urlguard";

describe("assertAllowedUrl", () => {
  it("allows ordinary http(s) when no allow-list is set", () => {
    expect(assertAllowedUrl("https://bucket.r2.cloudflarestorage.com/x?sig=1", "").hostname).toBe("bucket.r2.cloudflarestorage.com");
    expect(assertAllowedUrl("http://127.0.0.1:8000/v1/dev-storage/x", "").port).toBe("8000"); // local dev
  });
  it.each(["file:///etc/passwd", "ftp://x/y", "gopher://x", "javascript:alert(1)", "not a url", "http://169.254.169.254/latest/meta-data", "http://[fe80::1]/x", "http://metadata.google.internal/x"])("refuses %s", (u) => {
    expect(() => assertAllowedUrl(u, "")).toThrow();
  });
  it("with an allow-list, only listed hosts and wildcard subdomains pass", () => {
    const list = "acct.r2.cloudflarestorage.com,*.internal-storage.example";
    expect(() => assertAllowedUrl("https://acct.r2.cloudflarestorage.com/a", list)).not.toThrow();
    expect(() => assertAllowedUrl("https://eu.internal-storage.example/a", list)).not.toThrow();
    expect(() => assertAllowedUrl("https://evil.example/a", list)).toThrow();
    expect(() => assertAllowedUrl("https://acct.r2.cloudflarestorage.com.evil.example/a", list)).toThrow();
    expect(() => assertAllowedUrl("https://internal-storage.example.evil.com/a", list)).toThrow();
  });
});
