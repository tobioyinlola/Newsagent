import { describe, expect, it } from "vitest";
import { countWords, limitWords } from "./words";

const words = (n: number) => Array.from({ length: n }, (_, i) => `w${i + 1}`).join(" ");

describe("countWords", () => {
  it("counts words, not characters, and ignores extra spaces and line breaks", () => {
    expect(countWords("")).toBe(0);
    expect(countWords("   \n  ")).toBe(0);
    expect(countWords("one")).toBe(1);
    expect(countWords("  one   two\n\nthree\tfour ")).toBe(4);
  });
});

describe("limitWords", () => {
  it("leaves text within the limit exactly as typed, trailing space included", () => {
    expect(limitWords("a b c ", 250)).toBe("a b c ");
    expect(limitWords(words(250), 250)).toBe(words(250));
    expect(limitWords(`${words(250)} `, 250)).toBe(`${words(250)} `); // room to type a space after the 250th word
  });
  it("drops every word past the limit", () => {
    const cut = limitWords(words(260), 250);
    expect(countWords(cut)).toBe(250);
    expect(cut.endsWith("w250")).toBe(true);
    expect(limitWords(`${words(250)} extra`, 250)).toBe(words(250)); // the 251st word typed is not kept
  });
  it("keeps line breaks inside the kept words and trims a pasted wall of text", () => {
    expect(limitWords("one two\n\nthree four five", 3)).toBe("one two\n\nthree");
    expect(countWords(limitWords(words(2000), 250))).toBe(250);
  });
});
