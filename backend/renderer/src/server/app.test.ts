import { AddressInfo } from "node:net";
import { describe, expect, it } from "vitest";
import { createApp } from "./app";

async function withServer<T>(fn: (base: string) => Promise<T>, renderFn?: any, thumbFn?: any, lightFn?: any) {
  const server = createApp({ secret: "s3cret", renderFn, thumbFn, lightFn, normalizeFn: async () => {} }).listen(0);
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
  it("supports preview (scaled, named) and thumbnail outputs", async () => {
    const fs = await import("node:fs");
    const seen: any[] = [];
    const renderFn = async (o: any) => { seen.push(o.scale); fs.writeFileSync(o.outFile, "x"); };
    const thumbFn = async (_f: string, _p: any, out: string) => { fs.writeFileSync(out, "x"); };
    await withServer(async (b) => {
      const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
      const outputs = [
        { kind: "video", format: "16x9", name: "preview", scale: 0.5, width: 1920, height: 1080 },
        { kind: "thumbnail", format: "16x9", name: "thumbnail", width: 1920, height: 1080 },
      ];
      const { render_id } = await (await fetch(`${b}/renders`, { method: "POST", headers: h, body: JSON.stringify({ composition: "NewsStudio", props: {}, outputs, output_prefix: "p/final" }) })).json();
      for (let i = 0; i < 50; i++) {
        const s = await (await fetch(`${b}/renders/${render_id}`, { headers: h })).json();
        if (s.status === "succeeded") { expect(s.output_keys).toEqual(["p/final/preview.mp4", "p/final/thumbnail.png"]); expect(seen).toEqual([0.5]); return; }
        if (s.status === "failed") throw new Error(s.error);
        await new Promise((r) => setTimeout(r, 50));
      }
      throw new Error("did not finish");
    }, renderFn, thumbFn);
  });
  it("makes the light version from the finished HD file, without rendering again", async () => {
    const fs = await import("node:fs");
    const rendered: string[] = [];
    const made: { from: string; to: string }[] = [];
    const renderFn = async (o: any) => { rendered.push(o.outFile); fs.writeFileSync(o.outFile, "hd-bytes"); };
    const lightFn = async (from: string, to: string) => { made.push({ from, to }); expect(fs.readFileSync(from, "utf8")).toBe("hd-bytes"); fs.writeFileSync(to, "light"); };
    await withServer(async (b) => {
      const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
      const outputs = [
        { kind: "video", format: "16x9", width: 1920, height: 1080 },
        { kind: "video", format: "16x9", name: "16x9-light", variant: "light", width: 1920, height: 1080 },
      ];
      const { render_id } = await (await fetch(`${b}/renders`, { method: "POST", headers: h, body: JSON.stringify({ composition: "NewsStudio", props: {}, outputs, output_prefix: "p/final" }) })).json();
      for (let i = 0; i < 50; i++) {
        const s = await (await fetch(`${b}/renders/${render_id}`, { headers: h })).json();
        if (s.status === "succeeded") { expect(s.output_keys).toEqual(["p/final/16x9.mp4", "p/final/16x9-light.mp4"]); expect(rendered).toHaveLength(1); expect(made).toHaveLength(1); return; }
        if (s.status === "failed") throw new Error(s.error);
        await new Promise((r) => setTimeout(r, 50));
      }
      throw new Error("did not finish");
    }, renderFn, undefined, lightFn);
  });
  it("refuses a light version listed before its HD version", async () => {
    const renderFn = async () => {};
    await withServer(async (b) => {
      const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
      const outputs = [{ kind: "video", format: "16x9", name: "16x9-light", variant: "light", width: 1920, height: 1080 }];
      const { render_id } = await (await fetch(`${b}/renders`, { method: "POST", headers: h, body: JSON.stringify({ composition: "NewsStudio", props: {}, outputs, output_prefix: "p" }) })).json();
      await new Promise((r) => setTimeout(r, 200));
      expect((await (await fetch(`${b}/renders/${render_id}`, { headers: h })).json()).status).toBe("failed");
    }, renderFn);
  });
  it("rejects unsafe output names", async () => {
    const renderFn = async () => {};
    await withServer(async (b) => {
      const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
      const { render_id } = await (await fetch(`${b}/renders`, { method: "POST", headers: h, body: JSON.stringify({ composition: "NewsStudio", props: {}, outputs: [{ format: "16x9", name: "../evil", width: 1, height: 1 }], output_prefix: "p" }) })).json();
      await new Promise((r) => setTimeout(r, 200));
      expect((await (await fetch(`${b}/renders/${render_id}`, { headers: h })).json()).status).toBe("failed");
    }, renderFn);
  });

  it("rejects unknown compositions", async () => {
    await withServer(async (b) => {
      const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
      const r = await fetch(`${b}/renders`, { method: "POST", headers: h, body: JSON.stringify({ composition: "Evil", props: {}, outputs: [{ format: "16x9", width: 1, height: 1 }], output_prefix: "p" }) });
      expect(r.status).toBe(400);
    });
  });
  it("/process validates input, runs a job and exposes the result", async () => {
    const processFn = async () => { const fs = await import("node:fs"); const os = await import("node:os"); const d = fs.mkdtempSync(os.tmpdir() + "/pt-"); fs.writeFileSync(d + "/a.mp4", "v"); fs.writeFileSync(d + "/a.mp3", "a"); return { dir: d, video_path: d + "/a.mp4", audio_path: d + "/a.mp3", duration_s: 4.2, width: 640, height: 360, flags: ["dark_video"], stats: { mean_volume_db: -20, max_volume_db: -3, brightness: 10, speech_s: 3.9 } } as any; };
    const server = createApp({ secret: "s3cret", processFn }).listen(0);
    const b = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    try {
      const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
      for (const bad of [{}, { chunk_urls: [], kind: "video", ext: "webm", output_prefix: "p" }, { chunk_urls: ["http://x"], kind: "video", ext: "webm", output_prefix: "../p" }, { chunk_urls: ["http://x"], kind: "video", ext: "we/bm", output_prefix: "p" }]) {
        expect((await fetch(`${b}/process`, { method: "POST", headers: h, body: JSON.stringify(bad) })).status).toBe(400);
      }
      const { render_id } = await (await fetch(`${b}/process`, { method: "POST", headers: h, body: JSON.stringify({ chunk_urls: ["http://x/1"], kind: "video", ext: "webm", output_prefix: "projects/p1/takes/t1" }) })).json();
      for (let i = 0; i < 50; i++) {
        const s = await (await fetch(`${b}/renders/${render_id}`, { headers: h })).json();
        if (s.status === "succeeded") {
          expect(s.result).toMatchObject({ video_key: "projects/p1/takes/t1/answer.mp4", audio_key: "projects/p1/takes/t1/answer.mp3", duration_s: 4.2, flags: ["dark_video"] });
          return;
        }
        if (s.status === "failed") throw new Error(s.error);
        await new Promise((r) => setTimeout(r, 50));
      }
      throw new Error("did not finish");
    } finally { server.close(); }
  });
  it("/chromakey validates input and exposes the keyed result", async () => {
    const keyFn = async () => { const fs = await import("node:fs"); const os = await import("node:os"); const d = fs.mkdtempSync(os.tmpdir() + "/kt-"); fs.writeFileSync(d + "/o.webm", "w"); return { dir: d, path: d + "/o.webm", duration_s: 7.5, width: 640, height: 720 }; };
    const server = createApp({ secret: "s3cret", keyFn }).listen(0);
    const b = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    try {
      const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
      for (const bad of [{}, { url: "http://x", output_key: "../evil.webm" }, { url: "http://x", output_key: "p/a.mp4" }]) {
        expect((await fetch(`${b}/chromakey`, { method: "POST", headers: h, body: JSON.stringify(bad) })).status).toBe(400);
      }
      const { render_id } = await (await fetch(`${b}/chromakey`, { method: "POST", headers: h, body: JSON.stringify({ url: "http://x/v.mp4", output_key: "projects/p/anchor.webm" }) })).json();
      for (let i = 0; i < 50; i++) {
        const st = await (await fetch(`${b}/renders/${render_id}`, { headers: h })).json();
        if (st.status === "succeeded") { expect(st.result).toMatchObject({ key: "projects/p/anchor.webm", duration_s: 7.5 }); return; }
        if (st.status === "failed") throw new Error(st.error);
        await new Promise((r) => setTimeout(r, 50));
      }
      throw new Error("did not finish");
    } finally { server.close(); }
  });
  it("returns 429 with Retry-After when the queue is full, and recovers", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((r) => { release = r; });
    const fs = await import("node:fs");
    const renderFn: any = async ({ outFile }: any) => { await gate; fs.writeFileSync(outFile, "x"); };
    const server = createApp({ secret: "s3cret", renderFn, maxConcurrent: 1, maxQueue: 1, normalizeFn: async () => {} }).listen(0);
    const b = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
    const post = () => fetch(`${b}/renders`, { method: "POST", headers: h, body: JSON.stringify({ composition: "NewsStudio", props: {}, outputs: [{ format: "16x9", width: 1920, height: 1080 }], output_prefix: "p" }) });
    try {
      expect((await post()).status).toBe(202); // starts running
      expect((await post()).status).toBe(202); // waits in the queue (1 of 1)
      const busy = await post();
      expect(busy.status).toBe(429);
      expect(Number(busy.headers.get("retry-after"))).toBeGreaterThan(0);
      release();
      await new Promise((r) => setTimeout(r, 300));
      expect((await post()).status).toBe(202); // room again
    } finally { release(); server.close(); }
  });
  it("processes a founder's recording while a long render is still running", async () => {
    let release!: () => void;
    const blocked = new Promise<void>((r) => { release = r; });
    const renderFn = async () => { await blocked; };
    const processFn = async () => { throw new Error("quick job ran"); }; // fails fast: enough to prove it was not stuck behind the render
    const server = createApp({ secret: "s3cret", renderFn: renderFn as any, processFn: processFn as any, normalizeFn: async () => {} }).listen(0);
    const b = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
    const h = { "x-renderer-secret": "s3cret", "content-type": "application/json" };
    try {
      const outputs = [{ format: "16x9", width: 1920, height: 1080 }];
      await fetch(`${b}/renders`, { method: "POST", headers: h, body: JSON.stringify({ composition: "NewsStudio", props: {}, outputs, output_prefix: "p/a" }) });
      const { render_id } = await (await fetch(`${b}/renders`, { method: "POST", headers: h, body: JSON.stringify({ composition: "NewsStudio", props: {}, outputs, output_prefix: "p/b" }) })).json();
      const q = await (await fetch(`${b}/process`, { method: "POST", headers: h, body: JSON.stringify({ chunk_urls: ["http://x/1"], kind: "audio", ext: "webm", output_prefix: "t/1" }) })).json();
      let st: any;
      for (let i = 0; i < 50 && st?.status !== "failed"; i++) { await new Promise((r) => setTimeout(r, 20)); st = await (await fetch(`${b}/renders/${q.render_id}`, { headers: h })).json(); }
      expect(st.status).toBe("failed"); // it ran (and finished) although two renders are ahead of it
      expect((await (await fetch(`${b}/renders/${render_id}`, { headers: h })).json()).status).toBe("queued");
      const health = await (await fetch(`${b}/health`)).json();
      expect(health.render.queued).toBe(1);
    } finally { release(); server.close(); }
  });
});
