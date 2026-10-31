import { expect, it } from "vitest";
import { articleWordsValid, newsWordCount, scriptWordsValid } from "./newsDeskRules";
it("enforces article and short narration limits independently", () => {
  expect(newsWordCount(" \n one\t two   three ")).toBe(3);
  for (const words of [199, 301]) expect(articleWordsValid("word ".repeat(words))).toBe(false);
  for (const words of [200, 300]) expect(articleWordsValid("word ".repeat(words))).toBe(true);
  for (const words of [59, 96, 250]) expect(scriptWordsValid("word ".repeat(words))).toBe(false);
  for (const words of [60, 95]) expect(scriptWordsValid("word ".repeat(words))).toBe(true);
});
