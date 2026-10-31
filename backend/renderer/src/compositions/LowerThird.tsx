import { cardMotion } from "./broadcastMotion";
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { CF, CFSymbol, SANS } from "./theme";

// Broadcast lower third (news-channel style): a name box above the right end of a full-width headline bar, the bar opening
// with a Cover Founder NEWS block. Sits just above the ticker. The name box slides in after half a second; the headline stays.
export const LowerThird: React.FC<{ name?: string; title?: string; location?: string; headline?: string }> = ({ name, title, location, headline }) => {
  const frame = useCurrentFrame();
  const { width, height, fps, durationInFrames } = useVideoConfig();
  const portrait = height > width;
  const u = Math.min(width, height) / 1080;
  const barIn = cardMotion(frame, durationInFrames, fps);
  const nameIn = cardMotion(frame, durationInFrames, fps, .5, 6);
  const left = 48 * u, right = 48 * u, bottom = 72 * u + 26 * u; // clear of the ticker
  const barH = (portrait ? 96 : 78) * u;
  const headlineWidth = Math.max(240 * u, width - left - right - 282 * u);
  const headlineFont = Math.min((portrait ? 30 : 36) * u, Math.max(20 * u, (headlineWidth * 2) / (Math.max(1, headline?.length ?? 0) * .62)));
  if (!headline && !name) return null;
  return (
    <div style={{ position: "absolute", left, right, bottom, fontFamily: SANS }}>
      {name ? (
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 10 * u, opacity: nameIn, transform: `translateY(${(1 - nameIn) * 16 * u}px)` }}>
          <div style={{ background: CF.white, border: `${5 * u}px solid ${CF.green}`, padding: `${12 * u}px ${22 * u}px`, minWidth: 360 * u, maxWidth: portrait ? "95%" : "48%", overflowWrap: "anywhere" }}>
            <div style={{ color: CF.ink, fontWeight: 800, fontSize: 38 * u, lineHeight: 1.35 }}>{name}</div>
            {title ? (
              <div style={{ display: "flex", alignItems: "center", gap: 10 * u, marginTop: 6 * u, color: CF.ink, fontWeight: 700, fontSize: 22 * u, letterSpacing: 0.5 * u, textTransform: "uppercase", lineHeight: 1.355 }}>
                <span style={{ width: 12 * u, height: 12 * u, background: CF.green, border: `${2 * u}px solid ${CF.ink}`, flexShrink: 0 }} />
                {title}
              </div>
            ) : null}
            {location ? <div style={{ marginTop: 6 * u, color: CF.ink, opacity: 0.75, fontWeight: 600, fontSize: 21 * u, letterSpacing: 0.5 * u }}>{location}</div> : null}
          </div>
        </div>
      ) : null}
      {headline ? (
        <div style={{ display: "flex", alignItems: "stretch", minHeight: barH, opacity: barIn, transform: `scaleX(${0.85 + 0.15 * barIn})`, transformOrigin: "left center" }}>
          <div style={{ background: CF.navy, display: "flex", alignItems: "center", gap: 12 * u, padding: `0 ${20 * u}px`, borderBottom: `${6 * u}px solid ${CF.green}` }}>
            <CFSymbol height={barH * 0.56} />
            <span style={{ color: CF.green, fontWeight: 800, fontSize: 26 * u, letterSpacing: 2 * u }}>NEWS</span>
          </div>
          <div style={{ flex: 1, background: CF.white, display: "flex", alignItems: "center", padding: `${12 * u}px ${26 * u}px`, borderBottom: `${6 * u}px solid ${CF.green}`, overflow: "hidden" }}>
            <span style={{ color: CF.ink, fontWeight: 800, fontSize: headlineFont, lineHeight: 1.4, textTransform: "uppercase", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>{headline}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
};
