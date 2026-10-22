import React from "react";
import { AbsoluteFill, Easing, OffthreadVideo, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Chrome } from "./Chrome";
import { NewsProps } from "./types";

// Channel identity: Cover Founder (our own brand). Do not use any other real network's name, marks, music or trade dress.
export const NewsStudio: React.FC<NewsProps> = (p) => {
  const frame = useCurrentFrame();
  const { width, height, fps, durationInFrames } = useVideoConfig();
  const portrait = height > width;
  const u = Math.min(width, height) / 1080; // scale unit
  const slide = (start: number) =>
    interpolate(frame - start, [0, 15], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });

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

      <Chrome channel={p.channel} disclosures={p.disclosures} brand={p.brand} tickerLines={p.tickerLines} />

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
    </AbsoluteFill>
  );
};
