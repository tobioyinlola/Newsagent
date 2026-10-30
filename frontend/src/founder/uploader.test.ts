// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ChunkStore } from "./store";
import { TakeUploader } from "./uploader";
const mocks = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock("./guestApi", async importOriginal => ({ ...await importOriginal<typeof import("./guestApi")>(), guest: { POST: mocks.post } }));
const success = (data: unknown) => ({ response: new Response(null, { status: 200 }), data });
const failure = (status: number, detail: unknown) => ({ response: new Response(null, { status }), error: { detail } });
const take = { id: "test", status: "recording", kind: "video", chunks_received: [0, 1], flags: [], messages: [] };
beforeEach(() => { mocks.post.mockReset(); vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 200 }))); });
afterEach(() => vi.unstubAllGlobals());

it("reuploads server-reported missing chunks instead of requiring another take", async () => {
  let attempts = 0;
  mocks.post.mockImplementation(async (path: string, options: { body?: { indexes?: number[] } }) => {
    if (path.endsWith("chunk-urls")) return success({ urls: Object.fromEntries(options.body!.indexes!.map(i => [String(i), `https://storage.test/chunk-${i}`])) });
    if (path.endsWith("confirm")) return success(take);
    if (path.endsWith("complete")) {
      attempts++;
      return attempts === 1 ? failure(409, { error: "missing_chunks", message: "Some parts haven't arrived yet.", missing: [0] }) : success({ ...take, status: "uploaded" });
    }
    throw new Error(path);
  });
  const uploader = new TakeUploader("token", "test", new ChunkStore(), () => {});
  try {
    await uploader.add(0, new Blob(["one"])); await uploader.add(1, new Blob(["two"]));
    expect((await uploader.complete(2)).status).toBe("uploaded");
    expect(attempts).toBe(2);
    expect(vi.mocked(fetch).mock.calls.filter(c => String(c[0]).endsWith("chunk-0"))).toHaveLength(2);
    expect(vi.mocked(fetch).mock.calls.filter(c => String(c[0]).endsWith("chunk-1"))).toHaveLength(1);
  } finally { uploader.dispose(); }
});

it("exits a terminated upload instead of waiting forever", async () => {
  mocks.post.mockResolvedValue(failure(404, "This link is no longer valid."));
  const uploader = new TakeUploader("expired", "test", new ChunkStore(), () => {});
  try {
    await uploader.add(0, new Blob(["one"]));
    await expect(uploader.complete(1)).rejects.toThrow("This link is no longer valid.");
    expect(mocks.post.mock.calls.some(c => String(c[0]).endsWith("complete"))).toBe(false);
  } finally { uploader.dispose(); }
});
