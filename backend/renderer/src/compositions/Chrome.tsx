import { broadcastClock } from "./broadcastClock";
import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { NewsBackdrop } from "./NewsSet";
import { CF, CFLogo, MONO, SANS } from "./theme";

type ChromeProps = {
  channel: { name: string };
  disclosures: { tag: string; anchor: string };
  brand: { accent: string };
  tickerLines: string[];
  liveLocation?: string; // "Toronto, Canada": the LIVE badge, top-right, with a blinking light
  publishedLabel?: string; // "OCT 29, 2026 · 10:42 AM EDT": when this story was published, under the badge
};

// Where the top-right stack ends, so other top-right graphics (the web address) can sit below it.
export const TOP_RIGHT_STACK = 118;

// A dark plate keeps the channel bug and the mandatory labels readable on any studio, including a bright one.
const PLATE = "rgba(14, 22, 44, 0.78)";

// Elements shown on EVERY video, in every composition: the channel logo and the ticker. (The AI-presenter disclosure travels
// with the video's captions, description and share page rather than as an on-screen label.)
export const Chrome: React.FC<ChromeProps> = (p) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const u = Math.min(width, height) / 1080;
  const ticker = (p.tickerLines.filter(Boolean).join("   •   ") || "Cover Founder News") + "   •   ";
  const tickerW = ticker.length * 22 * u;
  const tickerX = -((frame * 3 * u) % tickerW);
  const blink = 0.55 + 0.45 * Math.cos((frame / fps) * Math.PI * 2 * 1.1); // the "on air" light: a slow pulse, about once a second
  return (
    <>
      {/* channel mark: the primary Cover Founder logo, top-left, on every video */}
      <div style={{ position: "absolute", top: 24 * u, left: 28 * u, background: CF.navy, padding: 8 * u, borderRadius: 4 * u }}>
        <CFLogo height={150 * u} />
      </div>
      {(p.liveLocation || p.publishedLabel) && (
        <div style={{ position: "absolute", top: 28 * u, right: 36 * u, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 * u, fontFamily: SANS }}>
          {p.liveLocation && (
            <div style={{ display: "flex", alignItems: "stretch", boxShadow: `0 ${4 * u}px ${14 * u}px rgba(0,0,0,0.35)` }}>
              <div style={{ background: "#E8352B", display: "flex", alignItems: "center", gap: 10 * u, padding: `${8 * u}px ${16 * u}px` }}>
                <span style={{ width: 16 * u, height: 16 * u, borderRadius: "50%", background: CF.white, opacity: blink, boxShadow: `0 0 ${14 * u * blink}px ${4 * u * blink}px rgba(255,255,255,0.85)` }} />
                <span style={{ color: CF.white, fontWeight: 800, fontSize: 30 * u, letterSpacing: 2 * u }}>LIVE</span>
              </div>
              <div style={{ background: CF.white, display: "flex", alignItems: "center", padding: `0 ${18 * u}px` }}>
                <span style={{ color: CF.ink, fontWeight: 700, fontSize: 28 * u, lineHeight: 1.4, maxWidth: width * .45, overflowWrap: "anywhere" }}>{p.liveLocation}</span>
              </div>
            </div>
          )}
          {p.publishedLabel && (
            <div style={{ background: PLATE, color: CF.white, fontFamily: MONO, fontWeight: 700, fontSize: 22 * u, letterSpacing: 1.5 * u, padding: `${6 * u}px ${14 * u}px`, textTransform: "uppercase" }}>{broadcastClock(p.publishedLabel, frame / fps)}</div>
          )}
        </div>
      )}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 72 * u, background: CF.ink, overflow: "hidden", borderTop: `${4 * u}px solid ${CF.green}` }}>
        <div style={{ whiteSpace: "nowrap", color: CF.white, fontFamily: SANS, fontSize: 32 * u, lineHeight: `${68 * u}px`, transform: `translateX(${tickerX}px)` }}>
          {ticker.repeat(Math.ceil((width * 2) / tickerW) + 2)}
        </div>
      </div>
    </>
  );
};

// The studio set behind the anchor: an original TV news set (see NewsSet.tsx).
export const Backdrop: React.FC<{ primary?: string; accent?: string }> = () => <NewsBackdrop />;
