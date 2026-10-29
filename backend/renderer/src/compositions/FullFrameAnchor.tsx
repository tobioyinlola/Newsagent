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

export const FullFrameAnchor: React.FC<{ src: string; muted?: boolean; covers?: boolean }> = ({ src, muted, covers = true }) => {
  const volume = useEdgeVolume();
  const { s, ox, oy } = useFit();
  const at = (r: { x: number; y: number; w: number; h: number }) => ({ left: ox + r.x * s, top: oy + r.y * s, width: r.w * s, height: r.h * s });
  return (
    <AbsoluteFill style={{ background: "#0f3f86" }}>
      <OffthreadVideo src={mediaUrl(src)} muted={muted} volume={volume} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      {covers && REFLECTIONS.map((r, i) => (
        <div key={i} style={{ position: "absolute", ...at(r), borderRadius: 14 * s, backdropFilter: `blur(${16 * s}px)`, background: "rgba(150,185,235,0.35)" }} />
      ))}
      {covers && SCREENS.map((r, i) => (
        <div key={i} style={{ position: "absolute", ...at(r), overflow: "hidden", background: "linear-gradient(180deg,#eaf1ff 0%,#9db8ec 55%,#3a5fb0 100%)", border: `${3 * s}px solid #dfe9fb` }}>
          <div style={{ position: "absolute", inset: 0, background: "repeating-linear-gradient(90deg, rgba(20,50,120,.22) 0 14%, rgba(255,255,255,.12) 14% 20%)" }} />
          <div style={{ position: "absolute", left: "6%", right: "6%", top: "24%", transform: "skewX(-8deg)", background: CF.peach, color: CF.ink, fontFamily: MONO, fontWeight: 700, fontSize: r.h * s * 0.2, letterSpacing: 2 * s, textAlign: "center", padding: `${r.h * s * 0.03}px 0` }}>FEATURED</div>
          <div style={{ position: "absolute", left: "14%", right: "6%", top: "55%", transform: "skewX(-8deg)", background: "#0f3f86", color: "#fff", fontFamily: SANS, fontWeight: 700, fontSize: r.h * s * 0.13, textAlign: "center", padding: `${r.h * s * 0.025}px 0` }}>STARTUP NEWS</div>
        </div>
      ))}
    </AbsoluteFill>
  );
};
