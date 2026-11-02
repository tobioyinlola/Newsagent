import React from "react";
import { AbsoluteFill, OffthreadVideo, useVideoConfig } from "remotion";
import { mediaUrl } from "./ClipScene";
import { useEdgeVolume } from "./SceneEdge";
import { CF, MONO, SANS } from "./theme";

// A presenter video that already contains its whole studio (the vendor animated a photo of the set), so it fills the frame.
// The source's own picture text (what the two side screens and the desk reflections say) is not ours to publish, so our
// boards are drawn over those areas.
const SRC_W = 1280;
const SRC_H = 720;

// Rectangles in the source picture (pixels of the 1280x720 video) that must be covered.
const SCREENS = [
  { x: 6, y: 76, w: 382, h: 258, side: "left" as const },
  { x: 904, y: 76, w: 372, h: 262, side: "right" as const },
];
const REFLECTIONS = [
  { x: 84, y: 566, w: 250, h: 78 },
  { x: 984, y: 570, w: 250, h: 76 },
];

const useFit = () => {
  const { width, height } = useVideoConfig();
  const s = Math.max(width / SRC_W, height / SRC_H); // object-fit: cover
  return { s, ox: (width - SRC_W * s) / 2, oy: (height - SRC_H * s) / 2 };
};

// `screenText`: optional words drawn on our boards, on the screens named in `screenTextOn` (the News Desk shows "BREAKING NEWS"
// on the left one only); business videos leave both boards plain. `offScreens`: screens shown with no board or text, as a
// switched-off screen in the studio's blue, so the picture's own text never shows (the News Desk's right screen).
export const FullFrameAnchor: React.FC<{ src: string; muted?: boolean; covers?: boolean; screenText?: string; screenTextOn?: ("left" | "right")[]; offScreens?: ("left" | "right")[] }> = ({ src, muted, covers = true, screenText, screenTextOn = ["left", "right"], offScreens = [] }) => {
  const volume = useEdgeVolume();
  const { s, ox, oy } = useFit();
  const at = (r: { x: number; y: number; w: number; h: number }) => ({ left: ox + r.x * s, top: oy + r.y * s, width: r.w * s, height: r.h * s });
  return (
    <AbsoluteFill style={{ background: "#0f3f86" }}>
      <OffthreadVideo src={mediaUrl(src)} muted={muted} volume={volume} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      {covers && REFLECTIONS.map((r, i) => (
        <div key={i} style={{ position: "absolute", ...at(r), borderRadius: 14 * s, backdropFilter: `blur(${16 * s}px)`, background: "rgba(150,185,235,0.35)" }} />
      ))}
      {covers && SCREENS.filter((r) => offScreens.includes(r.side)).map((r, i) => (
        <div key={`off-${i}`} style={{ position: "absolute", ...at(r), background: "linear-gradient(160deg,#2c63b8 0%,#17417f 55%,#0e2c5c 100%)", boxShadow: `inset 0 0 ${40 * s}px rgba(120,170,240,.35)` }} />
      ))}
      {covers && SCREENS.filter((r) => !offScreens.includes(r.side)).map((r, i) => (
        <div key={i} style={{ position: "absolute", ...at(r), overflow: "hidden", background: "linear-gradient(180deg,#eaf1ff 0%,#9db8ec 55%,#3a5fb0 100%)", border: `${3 * s}px solid #dfe9fb` }}>
          <div style={{ position: "absolute", inset: 0, background: "repeating-linear-gradient(90deg, rgba(20,50,120,.22) 0 14%, rgba(255,255,255,.12) 14% 20%)" }} />
          {screenText && screenTextOn.includes(r.side) && (
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", padding: 14 * s }}>
              <div style={{ background: "#eb464b", color: "white", fontFamily: SANS, fontWeight: 900, fontSize: 46 * s, lineHeight: 1.05, letterSpacing: 1 * s, textAlign: "center", padding: `${10 * s}px ${18 * s}px`, textTransform: "uppercase", boxShadow: `0 ${4 * s}px ${14 * s}px rgba(0,0,0,.35)` }}>{screenText}</div>
            </div>
          )}
        </div>
      ))}
    </AbsoluteFill>
  );
};
