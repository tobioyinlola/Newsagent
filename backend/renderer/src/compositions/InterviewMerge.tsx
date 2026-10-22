import React from "react";
import { AbsoluteFill, Audio, Freeze, Img, OffthreadVideo, Series, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Backdrop, Chrome } from "./Chrome";

export type Scene =
  | { type: "anchor" | "question"; src: string; seconds: number }
  | {
      type: "answer";
      seconds: number;
      src: string | null; // founder video (mp4); null for audio-only answers
      audioSrc?: string | null; // audio-only answers
      photoSrc?: string | null; // still shown for audio-only answers
      startFromSeconds?: number; // owner trim
      pipSrc: string; // the question clip, frozen on its first frame, shown as the anchor window
      founder: { name: string; title: string };
    };

export type MergeProps = {
  channel: { name: string };
  disclosures: { tag: string; anchor: string };
  brand: { primary: string; accent: string };
  tickerLines: string[];
  layout: "pip" | "split";
  scenes: Scene[];
  totalSeconds: number;
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

const AnchorShot: React.FC<{ src: string; muted?: boolean; height: string }> = ({ src, muted, height }) => (
  <OffthreadVideo src={url(src)} transparent muted={muted} style={{ height, objectFit: "contain" }} />
);

const AnchorScene: React.FC<{ src: string; portrait: boolean }> = ({ src, portrait }) => (
  <AbsoluteFill style={{ alignItems: "center", justifyContent: "flex-end", paddingBottom: portrait ? "18%" : "9%" }}>
    <AnchorShot src={src} height={portrait ? "58%" : "88%"} />
  </AbsoluteFill>
);

const AnswerScene: React.FC<{ scene: Extract<Scene, { type: "answer" }>; layout: "pip" | "split"; brand: MergeProps["brand"] }> = ({ scene, layout, brand }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const portrait = height > width;
  const u = Math.min(width, height) / 1080;
  const ltIn = interpolate(frame, [fps * 0.5, fps * 1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const ltOut = interpolate(frame, [fps * 4, fps * 4.5], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const founder = scene.src ? (
    <OffthreadVideo src={url(scene.src)} startFrom={Math.round((scene.startFromSeconds ?? 0) * fps)} style={{ width: "100%", height: "100%", objectFit: layout === "split" ? "cover" : "contain" }} />
  ) : (
    <>
      {scene.photoSrc ? <Img src={url(scene.photoSrc)} style={{ width: "100%", height: "100%", objectFit: "contain" }} /> : null}
      {scene.audioSrc ? <Audio src={url(scene.audioSrc)} startFrom={Math.round((scene.startFromSeconds ?? 0) * fps)} /> : null}
    </>
  );
  // Anchor "listening": the question clip frozen on its first frame and muted.
  const anchorBox = (
    <Freeze frame={0}>
      <div style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", background: `linear-gradient(160deg, ${brand.primary}, #050B1A 75%)`, display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
        <AnchorShot src={scene.pipSrc} muted height="100%" />
      </div>
    </Freeze>
  );

  const lowerThird = (
    <div style={{ position: "absolute", left: 48 * u, bottom: (portrait ? 20 : 14) + "%", opacity: ltIn * ltOut }}>
      <div style={{ background: "rgba(5,11,26,0.92)", borderLeft: `${10 * u}px solid ${brand.accent}`, padding: `${14 * u}px ${28 * u}px` }}>
        <div style={{ color: "#fff", fontSize: 44 * u, fontWeight: 800 }}>{scene.founder.name}</div>
        <div style={{ color: brand.accent, fontSize: 28 * u }}>{scene.founder.title}</div>
      </div>
    </div>
  );

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
      <div style={{ position: "absolute", right: 36 * u, top: portrait ? 130 * u : undefined, bottom: portrait ? undefined : 110 * u, width: width * pipW, height: width * pipW * 1.15, border: `${5 * u}px solid ${brand.accent}`, borderRadius: 16 * u, overflow: "hidden", boxShadow: "0 8px 30px rgba(0,0,0,0.5)" }}>{anchorBox}</div>
      {lowerThird}
    </AbsoluteFill>
  );
};

export const InterviewMerge: React.FC<MergeProps> = (p) => {
  const { fps, height, width } = useVideoConfig();
  const portrait = height > width;
  return (
    <AbsoluteFill style={{ fontFamily: "Inter, Helvetica, Arial, sans-serif", background: "#050B1A" }}>
      <Backdrop primary={p.brand.primary} accent={p.brand.accent} />
      <Series>
        {p.scenes.map((s, i) => (
          <Series.Sequence key={i} durationInFrames={Math.max(1, Math.round(s.seconds * fps))}>
            {s.type === "answer" ? <AnswerScene scene={s} layout={p.layout} brand={p.brand} /> : <AnchorScene src={s.src} portrait={portrait} />}
          </Series.Sequence>
        ))}
      </Series>
      <Chrome channel={p.channel} disclosures={p.disclosures} brand={p.brand} tickerLines={p.tickerLines} />
    </AbsoluteFill>
  );
};
