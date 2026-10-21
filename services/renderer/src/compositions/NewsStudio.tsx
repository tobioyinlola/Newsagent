import React from "react";
import { AbsoluteFill, Easing, OffthreadVideo, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { NewsProps } from "./types";

// Original fictional channel identity. Do not use any real network's name, marks, music or trade dress.
export const NewsStudio: React.FC<NewsProps> = (p) => {
  const frame = useCurrentFrame();
  const { width, height, fps, durationInFrames } = useVideoConfig();
  const portrait = height > width;
  const u = Math.min(width, height) / 1080; // scale unit
  const slide = (start: number) =>
    interpolate(frame - start, [0, 15], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });

  const ticker = p.tickerLines.join("   •   ") + "   •   ";
  const tickerW = ticker.length * 22 * u;
  const tickerX = -((frame * 3 * u) % tickerW);
  const lt = p.lowerThirds[Math.min(p.lowerThirds.length - 1, Math.floor(frame / (fps * 8)))];
  const ltStart = fps;
  const ltOut = interpolate(frame, [durationInFrames - 20, durationInFrames - 5], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: `linear-gradient(160deg, ${p.brand.primary}, #050B1A 75%)`, fontFamily: "Inter, Helvetica, Arial, sans-serif" }}>
      {/* studio set: abstract panels */}
      <AbsoluteFill>
        <div style={{ position: "absolute", left: "-10%", top: "8%", width: "60%", height: "70%", background: "rgba(255,255,255,0.05)", transform: "skewX(-12deg)" }} />
        <div style={{ position: "absolute", right: "-5%", top: "15%", width: "35%", height: "55%", background: "rgba(255,255,255,0.04)", transform: "skewX(-12deg)" }} />
        <div style={{ position: "absolute", left: 0, right: 0, bottom: portrait ? "32%" : "20%", height: 6 * u, background: p.brand.accent, opacity: 0.8 }} />
      </AbsoluteFill>

      {/* anchor */}
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-end", paddingBottom: portrait ? "18%" : "9%" }}>
        {p.anchorSrc ? (
          <OffthreadVideo src={p.anchorSrc.startsWith("http") ? p.anchorSrc : staticFile(p.anchorSrc)} transparent style={{ height: portrait ? "58%" : "88%", objectFit: "contain" }} />
        ) : (
          <svg viewBox="0 0 200 260" style={{ height: portrait ? "50%" : "78%" }}>
            <circle cx="100" cy="70" r="42" fill="#d9c2a7" />
            <path d="M20 260 C20 160 60 130 100 130 C140 130 180 160 180 260Z" fill="#1c2b4a" />
          </svg>
        )}
      </AbsoluteFill>

      {/* channel bug */}
      <div style={{ position: "absolute", top: 40 * u, left: 48 * u, display: "flex", gap: 12 * u, alignItems: "center" }}>
        <div style={{ width: 14 * u, height: 44 * u, background: p.brand.accent }} />
        <div style={{ color: "#fff", fontWeight: 800, fontSize: 30 * u, letterSpacing: 2 * u, textTransform: "uppercase" }}>{p.channel.name}</div>
      </div>

      {/* mandatory disclosures: always rendered, not controllable by users */}
      <div style={{ position: "absolute", top: 40 * u, right: 48 * u, textAlign: "right" }}>
        <div style={{ display: "inline-block", background: p.brand.accent, color: "#111", fontWeight: 900, fontSize: 28 * u, padding: `${6 * u}px ${18 * u}px`, textTransform: "uppercase", letterSpacing: 2 * u }}>{p.disclosures.tag}</div>
        <div style={{ color: "#fff", opacity: 0.9, fontSize: 22 * u, marginTop: 8 * u }}>{p.disclosures.anchor}</div>
      </div>

      {/* breaking-news style banner */}
      <div style={{ position: "absolute", left: 0, bottom: (portrait ? 31 : 19) * 1 + "%", transform: `translateX(${(1 - slide(5)) * -100}%)` }}>
        <div style={{ background: p.brand.accent, color: "#111", fontWeight: 900, fontSize: 34 * u, padding: `${8 * u}px ${28 * u}px`, textTransform: "uppercase", letterSpacing: 3 * u }}>
          Featured startup
        </div>
      </div>

      {/* lower third */}
      {lt && (
        <div style={{ position: "absolute", left: 48 * u, bottom: (portrait ? 20 : 11) + "%", opacity: slide(ltStart) * ltOut, transform: `translateY(${(1 - slide(ltStart)) * 30}px)` }}>
          <div style={{ background: "rgba(5,11,26,0.92)", borderLeft: `${10 * u}px solid ${p.brand.accent}`, padding: `${14 * u}px ${28 * u}px` }}>
            <div style={{ color: "#fff", fontSize: 44 * u, fontWeight: 800 }}>{lt.title}</div>
            <div style={{ color: p.brand.accent, fontSize: 28 * u }}>{lt.subtitle}</div>
          </div>
        </div>
      )}

      {/* ticker */}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 72 * u, background: "#050B1A", overflow: "hidden", borderTop: `${4 * u}px solid ${p.brand.accent}` }}>
        <div style={{ whiteSpace: "nowrap", color: "#fff", fontSize: 32 * u, lineHeight: `${68 * u}px`, transform: `translateX(${tickerX}px)` }}>
          {ticker.repeat(Math.ceil((width * 2) / tickerW) + 2)}
        </div>
      </div>
    </AbsoluteFill>
  );
};
