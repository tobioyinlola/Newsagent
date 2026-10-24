import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { mediaUrl } from "./ClipScene";
import { CF, MONO, SANS } from "./theme";

type Props = { scene: { src: string; kind: "image" | "video"; caption?: string; synthetic?: boolean; seconds: number } };

// Product footage: an image drifts slowly (so a still never feels frozen), a clip plays silent from its start.
// Anything AI-generated says so on screen; it is never passed off as real footage of the product.
export const BrollScene: React.FC<Props> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { width, height, durationInFrames } = useVideoConfig();
  const u = Math.min(width, height) / 1080;
  const zoom = interpolate(frame, [0, durationInFrames], [1, 1.12], { extrapolateRight: "clamp" });
  const capIn = interpolate(frame, [8, 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <AbsoluteFill style={{ top: 100 * u, bottom: 72 * u, overflow: "hidden" }}>
        {scene.kind === "image" ? (
          <Img src={mediaUrl(scene.src)} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})` }} />
        ) : (
          <OffthreadVideo src={mediaUrl(scene.src)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        )}
      </AbsoluteFill>
      {scene.synthetic && (
        <div style={{ position: "absolute", left: 48 * u, top: 120 * u, background: CF.peach, color: CF.ink, fontFamily: MONO, fontWeight: 700, fontSize: 24 * u, padding: `${6 * u}px ${16 * u}px`, textTransform: "uppercase", letterSpacing: 2 * u }}>
          AI-generated visual
        </div>
      )}
      {scene.caption ? (
        <div style={{ position: "absolute", left: 48 * u, bottom: 110 * u, opacity: capIn, transform: `translateY(${(1 - capIn) * 20}px)` }}>
          <div style={{ background: CF.ink, borderLeft: `${10 * u}px solid ${CF.green}`, padding: `${12 * u}px ${26 * u}px`, color: CF.white, fontFamily: SANS, fontWeight: 700, fontSize: 38 * u }}>{scene.caption}</div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
