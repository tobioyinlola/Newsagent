import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// A cut-out house presenter (Amara) sits in the male reporter's newsroom: the same plate as his picture, no desk.
describe("the newsroom plate", () => {
  const merge = readFileSync(new URL("./InterviewMerge.tsx", import.meta.url), "utf8");
  const studio = readFileSync(new URL("./NewsStudio.tsx", import.meta.url), "utf8");
  it("ships its picture", () => {
    expect(existsSync(new URL("../../public/newsroom-plate.jpg", import.meta.url))).toBe(true);
  });
  it("replaces the drawn set and the desk when a video asks for it, and only then", () => {
    expect(merge).toMatch(/p\.anchorFullFrame \? <AbsoluteFill style=\{\{ background: CF\.ink \}\} \/> : p\.anchorPlate \? <NewsroomPlate \/> : <Backdrop \/>/);
    expect(merge).toMatch(/plate \? \(\s*\/\/ on the newsroom plate the cut-out sits at the bottom edge/);
    expect(studio).toMatch(/p\.anchorPlate \? <NewsroomPlate \/> : <Backdrop \/>/);
    expect(studio).toMatch(/!p\.anchorPlate && <NewsDesk \/>/);
  });
});
