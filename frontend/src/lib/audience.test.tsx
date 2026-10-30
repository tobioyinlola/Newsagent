// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, cleanup } from "@testing-library/react";
import { addWatchRange, watchedSeconds, useVideoAudience, trackAudience, useStoryImpression } from "./audience";
beforeEach(() => {
  sessionStorage.clear(); localStorage.clear();
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  Object.defineProperty(navigator, "doNotTrack", { value: "0", configurable: true });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });
describe("audience counting", () => {
  it("merges overlapping watches without counting replayed content twice", () => {
    let ranges = addWatchRange([], 0, 6); ranges = addWatchRange(ranges, 3, 8); ranges = addWatchRange(ranges, 10, 14);
    expect(watchedSeconds(ranges)).toBe(12); expect(watchedSeconds(addWatchRange(ranges, 7, 11))).toBe(14); expect(ranges).toEqual([[0, 8], [10, 14]]);
  });
  it("deduplicates requests and respects privacy preferences", async () => {
    const slug = crypto.randomUUID(); await Promise.all([trackAudience(slug, "story_visit"), trackAudience(slug, "story_visit")]); await trackAudience(slug, "story_visit");
    expect(fetch).toHaveBeenCalledTimes(1);
    Object.defineProperty(navigator, "doNotTrack", { value: "1", configurable: true }); await trackAudience(crypto.randomUUID(), "story_visit"); expect(fetch).toHaveBeenCalledTimes(1);
  });
  it("counts engaged playback and completion, excluding paused changes", async () => {
    const video = document.createElement("video"); const ref = { current: video };
    Object.defineProperty(video, "paused", { value: false, configurable: true }); Object.defineProperty(video, "duration", { value: 12, configurable: true });
    const { unmount } = renderHook(() => useVideoAudience(ref, "watch-test", true)); video.dispatchEvent(new Event("playing"));
    for (let n = 1; n <= 12; n++) { video.currentTime = n; await act(async () => { video.dispatchEvent(new Event("timeupdate")); }); }
    await act(async () => { video.dispatchEvent(new Event("ended")); });
    expect(vi.mocked(fetch).mock.calls.map(c => JSON.parse(c[1]?.body as string).kind)).toEqual(["video_view", "video_complete"]); unmount(); vi.mocked(fetch).mockClear();
    const other = document.createElement("video"); Object.defineProperty(other, "duration", { value: 12 });
    renderHook(() => useVideoAudience({ current: other }, "paused-only", true));
    for (let n = 1; n <= 12; n++) { other.currentTime = n; other.dispatchEvent(new Event("timeupdate")); }
    await act(async () => { other.dispatchEvent(new Event("ended")); }); expect(fetch).not.toHaveBeenCalled();
  });
  it("counts impressions after the visible threshold lasts one second", async () => {
    vi.useFakeTimers(); let callback: IntersectionObserverCallback = () => {}; const disconnect = vi.fn();
    vi.stubGlobal("IntersectionObserver", class { constructor(cb: IntersectionObserverCallback) { callback = cb; } observe() {} disconnect = disconnect; });
    const ref = { current: document.createElement("div") }; const { unmount } = renderHook(() => useStoryImpression(ref, "impression-test"));
    const intersect = (value: boolean) => callback([{ isIntersecting: value, intersectionRatio: value ? .6 : 0 } as IntersectionObserverEntry], {} as IntersectionObserver);
    intersect(true); await act(async () => { vi.advanceTimersByTime(500); }); expect(fetch).not.toHaveBeenCalled();
    intersect(false); await act(async () => { vi.advanceTimersByTime(1000); }); expect(fetch).not.toHaveBeenCalled();
    intersect(true); await act(async () => { vi.advanceTimersByTime(1000); }); expect(fetch).toHaveBeenCalledTimes(1); unmount(); expect(disconnect).toHaveBeenCalled();
  });
});
