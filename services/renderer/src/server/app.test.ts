import { AddressInfo } from "node:net";
import { describe, expect, it } from "vitest";
import { createApp } from "./app";

async function withServer<T>(fn: (base: string) => Promise<T>, renderFn?: any) {
  const server = createApp({ secret: "s3cret", renderFn }).listen(0);
  try { return await fn(`http://127.0.0.1:${(server.address() as AddressInfo).port}`); } finally { server.close(); }
}

describe("renderer API", () => {
  it("rejects missing or wrong secret", async () => {
    await withServer(async (b) => {
      expect((await fetch(`${b}/renders/x`)).status).toBe(401);
      expect((await fetch(`${b}/renders/x`, { headers: { "x-renderer-secret": "nope" } })).status).toBe(401);
    });
  });
  it("validates request and runs a job to completion", async () => {
    const renderFn = async ({ outFile }: any) => { (await import("node:fs")).writeFileSync(outFile, "x"); };
    await withServer(async (b) => {
      const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
      expect((await fetch(`${b}/renders`, { method: "POST", headers: h, body: "{}" })).status).toBe(400);
      const r = await fetch(`${b}/renders`, { method: "POST", headers: h, body: JSON.stringify({
        composition: "NewsStudio", props: {}, outputs: [{ format: "16x9", width: 1920, height: 1080 }], output_prefix: "projects/p1/final" }) });
      const { render_id } = await r.json();
      for (let i = 0; i < 50; i++) {
        const s = await (await fetch(`${b}/renders/${render_id}`, { headers: h })).json();
        if (s.status === "succeeded") { expect(s.output_keys).toEqual(["projects/p1/final/16x9.mp4"]); return; }
        await new Promise((r) => setTimeout(r, 50));
      }
      throw new Error("job did not finish");
    }, renderFn);
  });
});
