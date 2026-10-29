import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile } from "remotion";
import { useEdgeVolume } from "./SceneEdge";
import { CF } from "./theme";

export const mediaUrl = (s: string) => (s.startsWith("http") ? s : staticFile(s));

// Presenter footage fills the frame (landscape clips are centre-cropped for 9:16); its own sound plays.
export const ClipScene: React.FC<{ src: string }> = ({ src }) => {
  const volume = useEdgeVolume();
  return (
    <AbsoluteFill style={{ background: CF.ink }}>
      <OffthreadVideo src={mediaUrl(src)} volume={volume} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    </AbsoluteFill>
  );
};
