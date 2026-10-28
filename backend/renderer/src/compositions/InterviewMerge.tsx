import React from "react";
import { AbsoluteFill, Audio, Freeze, Img, OffthreadVideo, Sequence, Series, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Backdrop, Chrome } from "./Chrome";
import { BrollScene } from "./BrollScene";
import { ClipScene } from "./ClipScene";
import { FullFrameAnchor } from "./FullFrameAnchor";
import { NewsDesk, SOFT_TOP, StudioProvider } from "./NewsSet";
import { CF, Fonts, MONO, SANS } from "./theme";

export type Scene =
  | { type: "anchor" | "question"; src: string; seconds: number }
  | { type: "clip"; src: string; seconds: number } // real presenter footage from the operator's library, full frame
  // the owner's product footage. `synthetic` shots (AI-generated) carry a mandatory on-screen label.
  | { type: "broll"; src: string; seconds: number; kind: "image" | "video"; caption?: string; synthetic?: boolean }
  | {
      type: "answer";
      seconds: number;
      src: string | null; // founder video (mp4); null for audio-only answers
      audioSrc?: string | null; // audio-only answers
      photoSrc?: string | null; // still shown for audio-only answers
      startFromSeconds?: number; // owner trim
      pipSrc: string; // the question clip, frozen on its first frame, shown as the anchor window
      founder: { name: string; title: string };
      // "answers column" layout: the question, its number, the founder's words timed to this answer (seconds from
      // the start of the trimmed answer) and a still taken while they spoke
      question?: string;
      questionNumber?: number;
      totalQuestions?: number;
      cues?: { start: number; end: number; text: string }[];
      posterSrc?: string | null;
      layout?: "pip" | "split" | "column" | "full"; // per-scene choice; falls back to the video's layout
    };

export type MergeProps = {
  channel: { name: string };
  disclosures: { tag: string; anchor: string };
  brand: { primary: string; accent: string };
  tickerLines: string[];
  layout: "pip" | "split" | "column" | "full";
  studio?: string;
  anchorFullFrame?: boolean;
  anchorCovers?: boolean;
  scenes: Scene[];
  totalSeconds: number;
  productUrl?: string; // the product's address, shown in the bottom-left corner from `productUrlFromSeconds` (the sign-off) to the end
  productUrlFromSeconds?: number;
};

export const defaultMergeProps: MergeProps = {
  channel: { name: "Cover Founder" },
  disclosures: { tag: "Featured", anchor: "AI-generated anchor" },
  brand: { primary: "#0B3D91", accent: "#F5A623" },
  tickerLines: ["FEATURED: Interview"],
  layout: "pip",
  scenes: [],
  totalSeconds: 10,
};

const url = (s: string) => (s.startsWith("http") ? s : staticFile(s));

const AnchorShot: React.FC<{ src: string; muted?: boolean; height: string; fullFrame?: boolean }> = ({ src, muted, height, fullFrame }) =>
  fullFrame ? (
    <OffthreadVideo src={url(src)} muted={muted} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "50% 22%" }} />
  ) : (
    <OffthreadVideo src={url(src)} transparent muted={muted} style={{ height, objectFit: "contain", ...SOFT_TOP }} />
  );

const AnchorScene: React.FC<{ src: string; portrait: boolean; fullFrame?: boolean; covers?: boolean }> = ({ src, portrait, fullFrame, covers }) =>
  fullFrame ? (
    <FullFrameAnchor src={src} covers={covers ?? true} />
  ) : (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-end", paddingBottom: portrait ? "16%" : "11%" }}>
    <AnchorShot src={src} height={portrait ? "66%" : "80%"} />
    <NewsDesk />
  </AbsoluteFill>
  );

// The founder's answer beside a column that shows the question and the founder's words as they say them.
// The text is timed from the transcript: a line appears when its cue starts, the current line is highlighted and the
// earlier ones dim, so what is on screen always matches what is being said.
const ColumnAnswer: React.FC<{ scene: Extract<Scene, { type: "answer" }>; founder: React.ReactNode }> = ({ scene, founder }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const portrait = height > width;
  const u = Math.min(width, height) / 1080;
  const t = frame / fps;
  const cues = (scene.cues ?? []).filter((c) => c.text.trim());
  const upto = cues.filter((c) => c.start <= t + 0.05);
  const current = upto.length ? upto[upto.length - 1] : null;
  const shown = upto.slice(portrait ? -3 : -4);
  const fade = (c: { start: number }) => interpolate(t - c.start, [0, 0.35], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const top = 132 * u; // clear of the channel bug and the disclosure labels
  const bottom = 72 * u;
  const panel: React.CSSProperties = portrait
    ? { left: 0, right: 0, bottom, height: `calc(100% - ${top + bottom}px - ${(height - top - bottom) * 0.5}px)`, padding: `${24 * u}px ${40 * u}px` }
    : { top, bottom, right: 0, width: width * 0.36, padding: `${34 * u}px ${40 * u}px` };
  const box: React.CSSProperties = portrait
    ? { top, left: 0, right: 0, height: (height - top - bottom) * 0.5 }
    : { top, bottom, left: 0, right: width * 0.36 };
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", ...box, background: "#000", overflow: "hidden" }}>{founder}</div>
      <div
        style={{
          position: "absolute", ...panel, background: CF.ink, overflow: "hidden", display: "flex", flexDirection: "column", gap: 18 * u,
          [portrait ? "borderTop" : "borderLeft"]: `${8 * u}px solid ${CF.green}`,
        }}
      >
        <div style={{ color: CF.green, fontFamily: MONO, fontWeight: 700, fontSize: 24 * u, letterSpacing: 3 * u, textTransform: "uppercase" }}>
          Question {scene.questionNumber ?? 1} of {scene.totalQuestions ?? 1}
        </div>
        <div style={{ color: CF.white, fontFamily: MONO, fontWeight: 700, fontSize: (portrait ? 34 : 40) * u, lineHeight: 1.2 }}>{scene.question}</div>
        <div style={{ height: 4 * u, background: CF.stripe, flexShrink: 0 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 18 * u, flexShrink: 0 }}>
          {scene.posterSrc ? (
            <Img src={url(scene.posterSrc)} style={{ width: 72 * u, height: 72 * u, objectFit: "cover", objectPosition: "50% 25%", borderRadius: 4 * u, border: `${3 * u}px solid ${CF.green}` }} />
          ) : null}
          <div>
            <div style={{ color: CF.white, fontFamily: SANS, fontWeight: 700, fontSize: 30 * u }}>{scene.founder.name}</div>
            <div style={{ color: CF.green, fontFamily: SANS, fontSize: 24 * u }}>{scene.founder.title}</div>
          </div>
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-start", gap: 14 * u, overflow: "hidden", paddingTop: 6 * u }}>
          {shown.map((c) => {
            const isCurrent = c === current;
            return (
              <div
                key={`${c.start}-${c.text}`}
                style={{
                  fontFamily: SANS, fontSize: (portrait ? 30 : 34) * u, lineHeight: 1.3,
                  color: isCurrent ? CF.white : "#A9A9A0",
                  fontWeight: isCurrent ? 700 : 400,
                  borderLeft: `${6 * u}px solid ${isCurrent ? CF.green : "transparent"}`,
                  paddingLeft: 16 * u,
                  opacity: isCurrent ? fade(c) : 1,
                }}
              >
                {c.text}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const AnswerScene: React.FC<{ scene: Extract<Scene, { type: "answer" }>; layout: MergeProps["layout"]; brand: MergeProps["brand"]; fullFrame?: boolean }> = ({ scene, layout, brand, fullFrame }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const portrait = height > width;
  const u = Math.min(width, height) / 1080;
  const ltIn = interpolate(frame, [fps * 0.5, fps * 1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const ltOut = interpolate(frame, [fps * 4, fps * 4.5], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const founder = scene.src ? (
    <OffthreadVideo src={url(scene.src)} startFrom={Math.round((scene.startFromSeconds ?? 0) * fps)} style={{ width: "100%", height: "100%", objectFit: layout === "pip" ? "contain" : "cover", objectPosition: layout === "column" ? "50% 28%" : "50% 50%" }} />
  ) : (
    <>
      {scene.photoSrc ? <Img src={url(scene.photoSrc)} style={{ width: "100%", height: "100%", objectFit: "contain" }} /> : null}
      {scene.audioSrc ? <Audio src={url(scene.audioSrc)} startFrom={Math.round((scene.startFromSeconds ?? 0) * fps)} /> : null}
    </>
  );
  // Anchor "listening": the question clip frozen on its first frame and muted.
  const anchorBox = (
    <Freeze frame={0}>
      <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", background: CF.ink, display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
        <AnchorShot src={scene.pipSrc} muted height="100%" fullFrame={fullFrame} />
      </div>
    </Freeze>
  );

  const lowerThird = (
    <div style={{ position: "absolute", left: 48 * u, bottom: (portrait ? 20 : 14) + "%", opacity: ltIn * ltOut }}>
      <div style={{ background: CF.ink, borderLeft: `${10 * u}px solid ${brand.accent}`, padding: `${14 * u}px ${28 * u}px` }}>
        <div style={{ color: CF.white, fontFamily: MONO, fontSize: 44 * u, fontWeight: 700 }}>{scene.founder.name}</div>
        <div style={{ color: CF.green, fontFamily: SANS, fontSize: 28 * u }}>{scene.founder.title}</div>
      </div>
    </div>
  );

  if (layout === "full") {
    // founder_fullscreen: the founder's own video fills the frame under the channel graphics
    return (
      <AbsoluteFill>
        <div style={{ position: "absolute", left: 0, right: 0, top: 100 * u, bottom: 72 * u, background: "#000" }}>{founder}</div>
        {lowerThird}
      </AbsoluteFill>
    );
  }
  if (layout === "column") {
    return <ColumnAnswer scene={scene} founder={founder} />;
  }
  if (layout === "split") {
    return (
      <AbsoluteFill style={{ flexDirection: portrait ? "column" : "row", paddingTop: 100 * u, paddingBottom: 72 * u }}>
        <div style={{ flex: 1, position: "relative", overflow: "hidden", background: "#000" }}>{founder}</div>
        <div style={{ flex: 1, position: "relative" }}>{anchorBox}</div>
        {lowerThird}
      </AbsoluteFill>
    );
  }
  const pipW = portrait ? 0.38 : 0.22;
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 0, right: 0, top: 100 * u, bottom: 72 * u, background: "#000" }}>{founder}</div>
      <div style={{ position: "absolute", right: 36 * u, top: portrait ? 130 * u : undefined, bottom: portrait ? undefined : 110 * u, width: width * pipW, height: width * pipW * 1.15, border: `${5 * u}px solid ${CF.green}`, borderRadius: 4 * u, overflow: "hidden" }}>{anchorBox}</div>
      {lowerThird}
    </AbsoluteFill>
  );
};

// The product's web address, in the corner while the presenter signs off, for anyone who wants to look it up.
const UrlBadge: React.FC<{ url: string }> = ({ url }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const u = Math.min(width, height) / 1080;
  const appear = interpolate(frame, [0, fps * 0.5], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", left: 36 * u, bottom: 96 * u, opacity: appear, transform: `translateY(${(1 - appear) * 24 * u}px)`, background: CF.ink, border: `${4 * u}px solid ${CF.green}`, borderRadius: 6 * u, padding: `${10 * u}px ${22 * u}px` }}>
      <div style={{ color: CF.green, fontFamily: MONO, fontWeight: 700, fontSize: 20 * u, letterSpacing: 2 * u, textTransform: "uppercase" }}>Find them online</div>
      <div style={{ color: CF.white, fontFamily: MONO, fontWeight: 700, fontSize: 36 * u, marginTop: 4 * u }}>{url}</div>
    </div>
  );
};

export const InterviewMerge: React.FC<MergeProps> = (p) => {
  const { fps, height, width } = useVideoConfig();
  const portrait = height > width;
  return (
    <StudioProvider studio={p.studio}>
    <AbsoluteFill style={{ fontFamily: SANS, background: CF.ink }}>
      <Fonts />
      <Backdrop />
      <Series>
        {p.scenes.map((s, i) => (
          <Series.Sequence key={i} durationInFrames={Math.max(1, Math.round(s.seconds * fps))}>
            {s.type === "answer" ? <AnswerScene scene={s} layout={s.layout ?? p.layout} brand={p.brand} fullFrame={p.anchorFullFrame} /> : s.type === "clip" ? <ClipScene src={s.src} /> : s.type === "broll" ? <BrollScene scene={s} /> : <AnchorScene src={s.src} portrait={portrait} fullFrame={p.anchorFullFrame} covers={p.anchorCovers} />}
          </Series.Sequence>
        ))}
      </Series>
      <Chrome channel={p.channel} disclosures={p.disclosures} brand={p.brand} tickerLines={p.tickerLines} />
      {p.productUrl && p.productUrlFromSeconds != null && (
        <Sequence from={Math.round(p.productUrlFromSeconds * fps)}>
          <UrlBadge url={p.productUrl} />
        </Sequence>
      )}
    </AbsoluteFill>
    </StudioProvider>
  );
};
