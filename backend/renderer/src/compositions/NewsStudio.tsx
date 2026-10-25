import React from "react";
import { AbsoluteFill, Easing, OffthreadVideo, Series, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { AnchorFigure } from "./AnchorFigure";
import { Backdrop, Chrome } from "./Chrome";
import { ClipScene } from "./ClipScene";
import { NewsDesk, SOFT_TOP, StudioProvider } from "./NewsSet";
import { CF, Fonts, MONO, SANS } from "./theme";
import { NewsProps } from "./types";

// Channel identity: Cover Founder (our own brand). Do not use any other real network's name, marks, music or trade dress.
// The studio over the AI presenter: backdrop, presenter, banner and lower third (the channel graphics are added by the caller).
const StudioBody: React.FC<NewsProps> = (p) => {
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
    <AbsoluteFill style={{ background: CF.ink, fontFamily: SANS }}>
      <Fonts />
      <Backdrop />

      {/* anchor */}
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-end", paddingBottom: portrait ? "16%" : "11%" }}>
        {p.anchorSrc ? (
          <OffthreadVideo src={p.anchorSrc.startsWith("http") ? p.anchorSrc : staticFile(p.anchorSrc)} transparent style={{ height: portrait ? "66%" : "80%", objectFit: "contain", ...SOFT_TOP }} />
        ) : (
          <AnchorFigure height={portrait ? "68%" : "86%"} />
        )}
      </AbsoluteFill>
      <NewsDesk />

      {/* breaking-news style banner */}
      <div style={{ position: "absolute", left: 0, bottom: (portrait ? 31 : 24.5) + "%", transform: `translateX(${(1 - slide(5)) * -100}%)` }}>
        <div style={{ background: CF.green, color: CF.ink, fontFamily: MONO, fontWeight: 700, fontSize: 34 * u, padding: `${8 * u}px ${28 * u}px`, textTransform: "uppercase", letterSpacing: 3 * u }}>
          Featured startup
        </div>
      </div>

      {/* lower third */}
      {lt && (
        <div style={{ position: "absolute", left: 48 * u, bottom: (portrait ? 20 : 11) + "%", opacity: slide(ltStart) * ltOut, transform: `translateY(${(1 - slide(ltStart)) * 30}px)` }}>
          <div style={{ background: CF.ink, borderLeft: `${10 * u}px solid ${p.brand.accent}`, padding: `${14 * u}px ${28 * u}px` }}>
            <div style={{ color: CF.white, fontFamily: MONO, fontSize: 44 * u, fontWeight: 700 }}>{lt.title}</div>
            <div style={{ color: CF.green, fontFamily: SANS, fontSize: 28 * u }}>{lt.subtitle}</div>
          </div>
        </div>
      )}
    </AbsoluteFill>
  );
};

// Optional presenter footage before and after the AI presenter. The channel bug, "Featured" tag, "AI-generated anchor"
// label and ticker stay on screen for the whole video, clips included (hard rule 2).
export const NewsStudio: React.FC<NewsProps> = (p) => {
  const { fps } = useVideoConfig();
  const frames = (s: number) => Math.max(1, Math.round(s * fps));
  return (
    <StudioProvider studio={p.studio}>
    <AbsoluteFill style={{ background: CF.ink, fontFamily: SANS }}>
      <Series>
        {p.introClip && <Series.Sequence durationInFrames={frames(p.introClip.seconds)}><ClipScene src={p.introClip.src} /></Series.Sequence>}
        <Series.Sequence durationInFrames={frames(p.anchorDurationSeconds)}><StudioBody {...p} /></Series.Sequence>
        {p.outroClip && <Series.Sequence durationInFrames={frames(p.outroClip.seconds)}><ClipScene src={p.outroClip.src} /></Series.Sequence>}
      </Series>
      <Chrome channel={p.channel} disclosures={p.disclosures} brand={p.brand} tickerLines={p.tickerLines} />
    </AbsoluteFill>
    </StudioProvider>
  );
};
