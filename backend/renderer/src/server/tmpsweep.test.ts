import { describe, expect, it } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { sweepTemp } from "./tmpsweep";

describe("sweepTemp", () => {
  it("removes old scratch directories and leaves recent or unrelated ones alone", () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "sweep-root-"));
    const old = path.join(root, "render-old"), fresh = path.join(root, "render-fresh"), other = path.join(root, "keepme");
    for (const d of [old, fresh, other]) fs.mkdirSync(d);
    const longAgo = new Date(Date.now() - 24 * 3600 * 1000);
    fs.utimesSync(old, longAgo, longAgo);
    fs.utimesSync(other, longAgo, longAgo);
    expect(sweepTemp(6 * 3600 * 1000, root)).toBe(1);
    expect(fs.existsSync(old)).toBe(false);
    expect(fs.existsSync(fresh)).toBe(true);
    expect(fs.existsSync(other)).toBe(true);
    fs.rmSync(root, { recursive: true, force: true });
  });
});
