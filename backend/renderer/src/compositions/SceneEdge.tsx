import React, { createContext, useContext } from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";

// Every scene is joined to the next by a very short dip: the picture fades up from the studio behind it and down again, and the
// sound ramps in and out with it. Cuts between separately recorded pieces (a presenter clip, a founder's answer, a library
// clip) otherwise land as a hard jump, often with a click where the sound starts or stops mid-wave. The timeline does not
// move: the dip happens inside each scene's own frames, so captions and on-screen timings stay exactly in step.
export const EDGE_FRAMES = 5; // about a sixth of a second

/** Gain (0 to 1) at `frame` of a scene `duration` frames long: ramps up over the first frames and down over the last. */
export function edgeGain(frame: number, duration: number, edge = EDGE_FRAMES): number {
  const e = Math.max(1, Math.min(edge, Math.floor(duration / 3))); // a very short scene gets a shorter dip
  const g = Math.min((frame + 1) / e, (duration - frame) / e, 1);
  return Math.max(0, g);
}

const EdgeVolume = createContext<((frame: number) => number) | null>(null);

/** For a media element inside a scene: pass the result as its `volume`. Outside a SceneEdge it is simply full volume. */
export function useEdgeVolume(): (frame: number) => number {
  return useContext(EdgeVolume) ?? (() => 1);
}

export const SceneEdge: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const gain = (f: number) => edgeGain(f, durationInFrames);
  return (
    <EdgeVolume.Provider value={gain}>
      <AbsoluteFill style={{ opacity: gain(frame) }}>{children}</AbsoluteFill>
    </EdgeVolume.Provider>
  );
};
