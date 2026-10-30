import { useEffect, type RefObject } from "react";
import { getToken } from "./auth";

type Kind = "impression" | "story_visit" | "share_visit" | "video_view" | "video_complete";
type Surface = "story" | "share";
const sent = new Set<string>();
const pending = new Map<string, Promise<boolean>>();

export async function trackAudience(identity: string, kind: Kind, surface: Surface = "story"): Promise<boolean> {
  if (!identity || navigator.doNotTrack === "1" || (navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl) return false;
  try {
    let session = sessionStorage.getItem("coverfounder.audience-session");
    if (!session) { session = crypto.randomUUID(); sessionStorage.setItem("coverfounder.audience-session", session); }
    const key = `${surface}:${identity}:${kind}:${new Date().toISOString().slice(0, 10)}`;
    if (sent.has(key)) return true;
    const inFlight = pending.get(key); if (inFlight) return inFlight;
    const token = getToken() ?? sessionStorage.getItem("newsagent.admin.token");
    const path = surface === "story" ? `public/stories/${encodeURIComponent(identity)}` : `share/${encodeURIComponent(identity)}`;
    const promise = fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/${path}/events`, { method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify({ kind, session_id: session }), keepalive: true })
      .then(r => { if (r.ok) { sent.add(key); return true; } return false; }).catch(() => false).finally(() => pending.delete(key));
    pending.set(key, promise); return promise;
  } catch { return false; } // Storage, privacy and analytics failures never interrupt a story or playback.
}

export function usePageAudience(identity: string, enabled: boolean, surface: Surface = "story") {
  useEffect(() => {
    if (!enabled) return;
    const visit = () => { if (document.visibilityState === "visible") void trackAudience(identity, surface === "story" ? "story_visit" : "share_visit", surface); };
    visit(); document.addEventListener("visibilitychange", visit);
    return () => document.removeEventListener("visibilitychange", visit);
  }, [identity, enabled, surface]);
}

export function useStoryImpression(ref: RefObject<HTMLElement>, slug: string) {
  useEffect(() => {
    const element = ref.current;
    if (!element || !slug || typeof IntersectionObserver === "undefined") return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let visible = false;
    let done = false;
    const stop = () => { if (timer) clearTimeout(timer); timer = undefined; };
    const check = () => {
      stop();
      if (visible && document.visibilityState === "visible" && !done) timer = setTimeout(() => { done = true; void trackAudience(slug, "impression"); }, 1000);
    };
    const observer = new IntersectionObserver(entries => { visible = entries.some(e => e.isIntersecting && e.intersectionRatio >= .5); check(); }, { threshold: [.5] });
    observer.observe(element); document.addEventListener("visibilitychange", check);
    return () => { stop(); observer.disconnect(); document.removeEventListener("visibilitychange", check); };
  }, [ref, slug]);
}

export type WatchRange = [number, number];
export function addWatchRange(ranges: WatchRange[], start: number, end: number): WatchRange[] {
  if (end <= start) return ranges;
  const result: WatchRange[] = [];
  for (const range of [...ranges, [start, end] as WatchRange].sort((a, b) => a[0] - b[0])) {
    const previous = result[result.length - 1];
    if (previous && range[0] <= previous[1] + .01) previous[1] = Math.max(previous[1], range[1]);
    else result.push([...range]);
  }
  return result;
}
export const watchedSeconds = (ranges: WatchRange[]) => ranges.reduce((sum, range) => sum + range[1] - range[0], 0);

export function useVideoAudience(ref: RefObject<HTMLVideoElement>, identity: string, enabled: boolean, surface: Surface = "story") {
  useEffect(() => {
    const video = ref.current;
    if (!video || !enabled) return;
    let ranges: WatchRange[] = [];
    let last = video.currentTime;
    let clock = performance.now();
    let viewed = false;
    let completed = false;
    const reset = () => { last = video.currentTime; clock = performance.now(); };
    const sample = () => {
      const now = performance.now(); const current = video.currentTime;
      const delta = current - last; const elapsed = (now - clock) / 1000;
      if (!video.seeking && (!video.paused || video.ended) && document.visibilityState === "visible" && delta > 0 && delta <= Math.max(2, elapsed * video.playbackRate + .5)) ranges = addWatchRange(ranges, last, current);
      last = current; clock = now;
      if (!viewed && watchedSeconds(ranges) >= 10) { viewed = true; void trackAudience(identity, "video_view", surface); }
    };
    const finish = async () => {
      sample();
      const duration = video.duration;
      if (!Number.isFinite(duration) || duration <= 0 || watchedSeconds(ranges) < duration * .9 || completed) return;
      completed = true; viewed = true;
      if (await trackAudience(identity, "video_view", surface)) await trackAudience(identity, "video_complete", surface);
    };
    video.addEventListener("timeupdate", sample); video.addEventListener("playing", reset); video.addEventListener("seeking", reset); video.addEventListener("seeked", reset); video.addEventListener("pause", reset); video.addEventListener("ended", finish); document.addEventListener("visibilitychange", reset);
    return () => { video.removeEventListener("timeupdate", sample); video.removeEventListener("playing", reset); video.removeEventListener("seeking", reset); video.removeEventListener("seeked", reset); video.removeEventListener("pause", reset); video.removeEventListener("ended", finish); document.removeEventListener("visibilitychange", reset); };
  }, [ref, identity, enabled, surface]);
}
