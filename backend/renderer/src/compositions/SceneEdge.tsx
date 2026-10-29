import React, { createContext, useContext } from "react";
import { AbsoluteFill, useVideoConfig } from "remotion";

// Every scene is joined to the next by a very short ramp in the SOUND only: a cut between separately recorded pieces (a presenter
// clip, a founder's answer, a library clip) can otherwise click where the sound starts or stops mid-wave. The PICTURE is never
// touched: it cuts cleanly, like a broadcast. (An earlier version also faded the picture, which let the studio set behind show
// through as a ghost at every cut; sceneEdge.test.ts guards against that coming back.) The timeline does not move: the ramp
// happens inside each scene's own frames, so captions and on-screen timings stay exactly in step.
export const EDGE_FRAMES = 5; // about a sixth of a second

/** Sound gain (0 to 1) at `frame` of a scene `duration` frames long: ramps up over the first frames and down over the last. */
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
  const { durationInFrames } = useVideoConfig();
  const gain = (f: number) => edgeGain(f, durationInFrames);
  return (
    <EdgeVolume.Provider value={gain}>
      <AbsoluteFill>{children}</AbsoluteFill>
    </EdgeVolume.Provider>
  );
};
