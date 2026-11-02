import React from "react";
import { AbsoluteFill, Audio, Easing, Img, OffthreadVideo, Sequence, Series, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { BrandIntro } from "./BrandIntro";
import { BrandOutro } from "./BrandOutro";
import { INTRO_SECONDS, OUTRO_SECONDS } from "./brand";
import { FullFrameAnchor } from "./FullFrameAnchor";
import { Fonts, SANS } from "./theme";

// Isolated composition: never used by NewsStudio or InterviewMerge.
export const BREAKING_FPS = 30;
export const STING_SECONDS = 2;
type Picture = { src: string; caption: string; motion: string; duration_s?: number };
export type BreakingProps = { headline: string; summary: string; anchorSrc: string; presenterFrames: number; pictures: Picture[]; anchorCovers?: boolean };
// The words on our boards when a presenter's studio picture has its own screens to cover (their AI-made text is misspelled).
export const SCREEN_TEXT = "Breaking News";
export const defaultBreakingProps: BreakingProps = { headline: "CF Technology Breaking News", summary: "Cover Founder News", anchorSrc: "", presenterFrames: 900, pictures: [] };
export function breakingFrames(props: BreakingProps): number {
  if (!Number.isInteger(props.presenterFrames) || props.presenterFrames <= 0 || props.presenterFrames > 47 * BREAKING_FPS) throw new Error("News Desk presenter must fit within 47 seconds");
  const total = props.presenterFrames + (INTRO_SECONDS + OUTRO_SECONDS + STING_SECONDS) * BREAKING_FPS;
  if (total > 60 * BREAKING_FPS) throw new Error("News Desk video exceeds the strict one-minute maximum");
  return total;
}
export function validateBreakingProps(value: unknown): asserts value is BreakingProps {
  const p = value as BreakingProps;
  breakingFrames(p);
  if (typeof p.anchorSrc !== "string" || !p.anchorSrc || typeof p.headline !== "string" || p.headline.length > 180 || !Array.isArray(p.pictures) || !p.pictures.length || p.pictures.length > 15 || p.pictures.some(i => typeof i.src !== "string" || !i.src)) throw new Error("News Desk needs a presenter, headline and verified image sequence");
}
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.bezier(.22, 1, .36, 1);
const Sting: React.FC = () => {
  const f = useCurrentFrame(); const { width, height } = useVideoConfig();
  const enter = interpolate(f, [0, 15], [width, 0], { ...clamp, easing: ease });
  const exit = interpolate(f, [46, 60], [0, -width], { ...clamp, easing: ease });
  return <AbsoluteFill style={{ background: "#191a30", justifyContent: "center", fontFamily: SANS, overflow: "hidden" }}>
    <Audio src={staticFile("audio/news-breaking.wav")} volume={0.7} />
    <div style={{ position: "absolute", background: "#c0fe73", inset: 0, transform: `translateX(${enter + exit}px) skewX(-12deg)` }} />
    <div style={{ zIndex: 1, padding: width * .07, opacity: interpolate(f, [4, 14, 47, 59], [0, 1, 1, 0], clamp), transform: `translateX(${interpolate(f, [4, 20], [90, 0], { ...clamp, easing: ease })}px)` }}>
      <p style={{ color: "#222", letterSpacing: 8, fontSize: width * .02, fontWeight: 800 }}>COVER FOUNDER NEWS</p>
      <h1 style={{ color: "#222", lineHeight: 1.02, fontSize: Math.min(width * .092, height * .16), margin: "24px 0", fontWeight: 900 }}>BREAKING<br />NEWS</h1>
      <p style={{ color: "#222", fontSize: width * .024 }}>TECHNOLOGY • BUSINESS • INNOVATION</p>
    </div>
  </AbsoluteFill>;
};

export type Cutaway = { from: number; duration: number; picture: number };
export function breakingCutaways(frames: number, pictures: number, requested: number[] = []): Cutaway[] {
  // Leave the presenter visible at both ends and between images; the continuous audio is never restarted.
  const count = Math.min(pictures, 4, Math.max(0, Math.floor((frames - 8 * 30) / (7 * 30))));
  if (!count) return [];
  const slot = (frames - 8 * 30) / count;
  const duration = Math.min(5 * 30, Math.floor(slot * .6));
  return Array.from({ length: count }, (_, i) => ({ from: Math.floor(5 * 30 + i * slot), duration: Math.min(duration, Math.max(30, Math.round((requested[i] || 5) * 30))), picture: i }));
}
const MotionPicture: React.FC<{ picture: Picture; frames: number }> = ({ picture, frames }) => {
  const f = useCurrentFrame(); const t = interpolate(f, [0, Math.max(1, frames - 1)], [0, 1], clamp);
  const zoom = picture.motion === "static" ? 1 : picture.motion === "slow_zoom_out" ? 1.09 - t * .07 : 1.02 + t * .07;
  const pan = picture.motion === "pan_left" ? 3 - 6 * t : picture.motion === "pan_right" ? -3 + 6 * t : 0;
  const opacity = interpolate(f, [0, 10, frames - 10, frames - 1], [0, 1, 1, 0], { ...clamp, easing: ease });
  return <AbsoluteFill style={{ background: "#191a30", opacity, overflow: "hidden" }}>
    <Img src={picture.src} style={{ width: "100%", height: "100%", objectFit: "contain", transform: `translateX(${pan}%) scale(${zoom})` }} />
    {picture.caption && <div style={{ position: "absolute", bottom: "32%", left: "5%", maxWidth: "82%", background: "#222d", color: "white", padding: "12px 22px", fontSize: 25, lineHeight: 1.4 }}>{picture.caption}</div>}
  </AbsoluteFill>;
};
const Report: React.FC<BreakingProps> = p => {
  const f = useCurrentFrame(); const { width, height } = useVideoConfig();
  const cutaways = breakingCutaways(p.presenterFrames, p.pictures.length, p.pictures.map(picture => picture.duration_s || 5));
  const card = interpolate(f, [0, 18], [height * .24, 0], { ...clamp, easing: ease });
  return <AbsoluteFill style={{ background: "#191a30", fontFamily: SANS }}>
    {p.anchorSrc && (p.anchorCovers ? <FullFrameAnchor src={p.anchorSrc} covers screenText={SCREEN_TEXT} /> : <OffthreadVideo src={p.anchorSrc} style={{ width: "100%", height: "100%", objectFit: "cover" }} />)}
    {cutaways.map(c => <Sequence key={c.from} from={c.from} durationInFrames={c.duration}><MotionPicture picture={p.pictures[c.picture]} frames={c.duration} /></Sequence>)}
    <div style={{ position: "absolute", top: "4%", left: "4%", background: "#222", border: "2px solid #c0fe73", color: "#c0fe73", padding: "12px 18px", fontSize: width * .018, fontWeight: 800 }}>CF NEWS</div>
    <div style={{ position: "absolute", top: "4%", right: "4%", background: "#eb464b", color: "white", padding: "12px 18px", fontSize: width * .015, fontWeight: 800 }}>BREAKING NEWS</div>
    <div style={{ position: "absolute", left: 0, right: 0, bottom: "4%", transform: `translateY(${card}px)` }}>
      <div style={{ marginLeft: "4%", background: "#c0fe73", color: "#222", width: "fit-content", padding: "10px 22px", fontSize: width * .016, fontWeight: 800 }}>CF TECHNOLOGY BREAKING NEWS</div>
      <div style={{ padding: "18px 4% 22px", background: "#222f", borderBottom: "5px solid #c0fe73", color: "white", fontSize: width * (p.headline.length > 120 ? .024 : .03), lineHeight: 1.26, fontWeight: 800, overflowWrap: "anywhere" }}>{p.headline}</div>
    </div>
  </AbsoluteFill>;
};
export const NewsBreaking: React.FC<BreakingProps> = p => {
  breakingFrames(p);
  return <AbsoluteFill><Fonts /><Series>
    <Series.Sequence durationInFrames={INTRO_SECONDS * 30}><BrandIntro /></Series.Sequence>
    <Series.Sequence durationInFrames={STING_SECONDS * 30}><Sting /></Series.Sequence>
    <Series.Sequence durationInFrames={p.presenterFrames}><Report {...p} /></Series.Sequence>
    <Series.Sequence durationInFrames={OUTRO_SECONDS * 30}><BrandOutro /></Series.Sequence>
  </Series></AbsoluteFill>;
};
