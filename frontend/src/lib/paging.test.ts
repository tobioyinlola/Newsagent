import { describe, expect, it } from "vitest";
import { pageCount, pageWindow, rangeText, totalOf } from "./paging";

describe("page numbers", () => {
  it("counts pages, never fewer than one", () => {
    expect(pageCount(0, 25)).toBe(1);
    expect(pageCount(25, 25)).toBe(1);
    expect(pageCount(26, 25)).toBe(2);
    expect(pageCount(112, 25)).toBe(5);
  });
  it("shows the first, the last and the neighbours, with gaps marked", () => {
    expect(pageWindow(0, 1)).toEqual([0]);
    expect(pageWindow(0, 5)).toEqual([0, 1, 2, 3, 4]);
    expect(pageWindow(0, 20)).toEqual([0, 1, "…", 19]);
    expect(pageWindow(10, 20)).toEqual([0, "…", 9, 10, 11, "…", 19]);
    expect(pageWindow(19, 20)).toEqual([0, "…", 18, 19]);
    expect(pageWindow(2, 6)).toEqual([0, 1, 2, 3, 4, 5]); // a one-page gap is filled rather than hidden
  });
});

describe("what is on screen", () => {
  it("says which rows are showing", () => {
    expect(rangeText(0, 0, 25, "customers")).toBe("No customers");
    expect(rangeText(112, 0, 25, "customers")).toBe("Showing 1 to 25 of 112 customers");
    expect(rangeText(112, 4, 25, "customers")).toBe("Showing 101 to 112 of 112 customers");
    expect(rangeText(1500, 0, 100)).toBe("Showing 1 to 100 of 1,500 results");
  });
  it("reads the total from the header, then the body, then what came back", () => {
    expect(totalOf(new Headers({ "X-Total-Count": "42" }), [], 10)).toBe(42);
    expect(totalOf(new Headers(), { total: 7 }, 3)).toBe(7);
    expect(totalOf(new Headers(), [], 3, 20)).toBe(23);
    expect(totalOf(undefined, { items: [] }, 0)).toBe(0);
  });
});
