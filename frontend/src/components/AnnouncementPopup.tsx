import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { AnnouncementCard } from "./AnnouncementCard";
import { useTours } from "./tour/TourProvider";

type Announcement = { id: string; title: string; message: string; button_label: string; button_url: string; shows_until: string };
const SNOOZED = "newsagent.announcements.snoozed"; // closed for now (this visit); the server remembers the ones closed for good
const read = (): string[] => { try { const v = JSON.parse(sessionStorage.getItem(SNOOZED) ?? "[]"); return Array.isArray(v) ? v : []; } catch { return []; } };

/** The announcement the team has set live: shown after sign-in for as long as the team chose, until the person closes it for good.
 *  "Remind me later" hides it for this visit only. On a phone it slides up from the bottom. */
export function AnnouncementPopup() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const tours = useTours();
  const [snoozed, setSnoozed] = useState<string[]>(read);
  const list = useQuery({ queryKey: ["announcements"], queryFn: () => unwrap(api.GET("/v1/me/announcements")) as unknown as Promise<Announcement[]>, retry: false, staleTime: 60_000, refetchOnWindowFocus: false });
  const a = (Array.isArray(list.data) ? list.data : []).find((x) => !snoozed.includes(x.id));
  const primary = useRef<HTMLButtonElement>(null);
  const waiting = !!tours?.activeId; // a guided tour is on screen: the announcement waits its turn
  const shownId = a?.id;
  const counted = useRef<string | null>(null);
  useEffect(() => { // the team sees how many people were shown it: once per person, however often it appears
    if (shownId && !waiting && counted.current !== shownId) { counted.current = shownId; void api.POST("/v1/me/announcements/{announcement_id}/seen", { params: { path: { announcement_id: shownId } } }).catch(() => undefined); }
  }, [shownId, waiting]);
  useEffect(() => { if (shownId && !waiting) primary.current?.focus({ preventScroll: true }); }, [shownId, waiting]);
  if (!a || waiting) return null;
  const later = () => { const next = [...snoozed, a.id]; setSnoozed(next); try { sessionStorage.setItem(SNOOZED, JSON.stringify(next)); } catch { /* lasts until reload */ } };
  const close = () => { void api.POST("/v1/me/announcements/{announcement_id}/dismiss", { params: { path: { announcement_id: a.id } } }).finally(() => { void qc.invalidateQueries({ queryKey: ["announcements"] }); }); later(); };
  const go = () => { void api.POST("/v1/me/announcements/{announcement_id}/click", { params: { path: { announcement_id: a.id } } }).catch(() => undefined); const url = a.button_url; close(); if (url.startsWith("/")) nav(url); else window.open(url, "_blank", "noopener,noreferrer"); };
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/60 sm:items-center sm:p-4" onKeyDown={(e) => { if (e.key === "Escape") later(); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="announcement-title" className="flex max-h-[92dvh] w-full justify-center overflow-y-auto pb-[env(safe-area-inset-bottom)] sm:pb-0">
        <AnnouncementCard a={{ ...a }}>
          <span id="announcement-title" className="sr-only">{a.title}</span>
          <div className="sticky bottom-0 -mx-5 -mb-5 flex flex-col gap-3 border-t border-line bg-white px-5 py-3 sm:flex-row-reverse sm:items-center sm:justify-between">
            <button type="button" ref={primary} className="min-h-11 rounded-sm border-2 border-ink bg-brand-green px-5 py-2 text-sm font-bold hover:bg-ink hover:text-brand-green" onClick={a.button_label ? go : close}>{a.button_label || "Got it"}</button>
            <div className="flex flex-wrap items-center justify-center gap-5 sm:justify-start">
              {a.button_label && <button type="button" className="min-h-11 text-sm font-semibold underline" onClick={close}>Got it</button>}
              <button type="button" className="min-h-11 text-sm font-semibold underline" onClick={later}>Remind me later</button>
            </div>
          </div>
        </AnnouncementCard>
      </div>
    </div>
  );
}
