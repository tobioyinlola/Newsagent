import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { localizeMedia } from "./localize";

describe("localizeMedia", () => {
  it("downloads each remote link once and points the props at the local copies", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "loc-"));
    const seen: string[] = [];
    const fake = (async (u: string) => { seen.push(u); return new Response(`data:${u}`); }) as unknown as typeof fetch;
    const props = { scenes: [{ src: "https://r2.example/a.mp4?sig=1" }, { src: "https://r2.example/a.mp4?sig=1", pipSrc: "https://r2.example/q.webm?x" }], keep: "http://127.0.0.1:4000/x", n: 3 };
    const out = await localizeMedia(props, dir, (f) => `http://local/${f}`, fake);
    expect(seen).toHaveLength(2);
    expect(out.scenes[0].src).toBe(out.scenes[1].src);
    expect(out.scenes[0].src).toMatch(/^http:\/\/local\/\d+\.mp4$/);
    expect((out.scenes[1] as { pipSrc: string }).pipSrc).toMatch(/\.webm$/);
    expect(out.keep).toBe("http://127.0.0.1:4000/x");
    expect(fs.readdirSync(dir)).toHaveLength(2);
  });

  it("fails with a reason when a file can't be downloaded", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "loc-"));
    const fake = (async () => new Response("no", { status: 403 })) as unknown as typeof fetch;
    await expect(localizeMedia({ src: "https://r2.example/a.mp4" }, dir, (f) => f, fake)).rejects.toThrow(/403/);
  });
});
