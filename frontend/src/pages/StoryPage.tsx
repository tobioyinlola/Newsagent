import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { PressRelease, type Story } from "../components/PressRelease";
import { clock, dayOf, STORIES_PATH, StoryRow, useStories } from "../components/StoryCards";
import { Cta, SiteShell } from "./Landing";

export function StoryPage() {
  const { slug = "" } = useParams();
  const q = useQuery({ queryKey: ["public-story", slug], queryFn: () => unwrap(api.GET("/v1/public/stories/{slug}", { params: { path: { slug } } })), retry: false });
  const more = useStories(12);
  const video = useRef<HTMLVideoElement>(null);
  const [copied, setCopied] = useState(false);
  const [silent, setSilent] = useState(false); // the browser only allowed it to start muted
  // Autoplay with sound. Arriving from a click on a story card counts as the visitor's go-ahead, so this normally just plays; if
  // the browser refuses (a link opened straight into the page), play muted instead and offer a one-tap "Turn sound on".
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    v.muted = false;
    setSilent(false);
    v.play().catch(() => { v.muted = true; setSilent(true); void v.play().catch(() => undefined); });
  }, [q.data?.video_url]);
  // If the browser did start it muted, the visitor's first touch, tap or key anywhere on the page turns the sound on.
  useEffect(() => {
    if (!silent) return;
    const on = () => { const v = video.current; if (v) { v.muted = false; v.volume = 1; } setSilent(false); };
    const events = ["pointerdown", "keydown", "touchstart"] as const;
    events.forEach((e) => window.addEventListener(e, on, { once: true }));
    return () => events.forEach((e) => window.removeEventListener(e, on));
  }, [silent]);
  const soundOn = () => { const v = video.current; if (!v) return; v.muted = false; v.volume = 1; setSilent(false); void v.play().catch(() => undefined); };
  const s = q.data;
  return (
    <SiteShell>
      <main className="px-4 py-8 md:px-8">
        <div className="mx-auto max-w-4xl">
          <Link to={STORIES_PATH} className="text-sm text-white/70 hover:text-brand-green">← Latest stories</Link>
          {q.isLoading && <p aria-busy="true" className="mt-6 text-white/70">Loading…</p>}
          {q.isError && (
            <div className="mt-8 border border-white/15 p-8 text-center">
              <h1 className="text-2xl font-bold text-white">This story isn't available.</h1>
              <p className="mt-2 text-white/70">It may have been taken down by its publisher.</p>
              <div className="mt-5 flex justify-center"><Cta to={STORIES_PATH} primary>See the latest stories</Cta></div>
            </div>
          )}
          {s && (
            <>
              <div className="mt-4 overflow-hidden rounded-sm border border-white/15 bg-black">
                <video ref={video} key={s.video_url} src={s.video_url} poster={s.thumbnail_url ?? undefined} controls autoPlay playsInline preload="auto" onVolumeChange={(e) => { if (!e.currentTarget.muted) setSilent(false); }} className="aspect-video w-full bg-black" aria-label={`Video: ${s.title}`} />
              </div>
              <p className="mt-2 text-xs text-white/60">
                {silent && <button type="button" className="mr-2 rounded-sm bg-brand-green px-2 py-1 font-bold text-ink" onClick={soundOn}>Turn sound on</button>}
                {silent ? "Your browser started it without sound. " : ""}{s.disclosure}
              </p>
              <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-white/70">
                <span className="font-semibold text-white">{s.company}</span>
                {s.industry && <span>· {s.industry}</span>}
                <span>· {dayOf(s.published_at)}</span>
                {s.duration_s != null && <span>· {clock(s.duration_s)}</span>}
                <button type="button" className="ml-auto rounded-sm border border-white/40 px-3 py-1 text-xs font-bold text-white hover:border-brand-green hover:text-brand-green" onClick={async () => { try { await navigator.clipboard.writeText(window.location.href); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); } }}>{copied ? "Link copied" : "Copy link"}</button>
              </div>
              <div className="mt-8 border-t border-white/10 pt-8">
                <PressRelease
                  tone="dark"
                  headingLevel={2}
                  story={{ headline: s.title, dek: s.summary, sections: s.sections as Story["sections"], dateline: s.dateline, about: s.about, company: s.company, social: { hook: "", post: "", hashtags: [] } }}
                  pictures={s.pictures.map((p) => ({ url: p.url, caption: p.caption ?? "" }))}
                />
              </div>
              <div className="mt-12 border border-white/15 p-6 text-center">
                <p className="text-lg font-bold text-white">Have news of your own?</p>
                <p className="mt-1 text-sm text-white/70">We interview you, make the video and write the press release. It appears here.</p>
                <div className="mt-4 flex justify-center"><Cta to="/signup" primary>Publish your free story!</Cta></div>
              </div>
              {(more.data ?? []).filter((c) => c.slug !== s.slug).length > 0 && <div className="mt-10"><StoryRow title="More stories" cards={(more.data ?? []).filter((c) => c.slug !== s.slug)} /></div>}
            </>
          )}
        </div>
      </main>
    </SiteShell>
  );
}
