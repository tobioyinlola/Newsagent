/** A smooth entrance and exit entirely inside the scene. Short scenes shorten the ramps. */
export function cardMotion(frame: number, duration: number, fps: number, delay = 0, holdSeconds?: number): number {
  const start = Math.min(delay * fps, Math.max(0, duration / 5));
  const end = holdSeconds === undefined ? duration : Math.min(duration, start + holdSeconds * fps);
  const ramp = Math.max(1, Math.min(fps * .4, (end - start) / 3));
  const enter = Math.max(0, Math.min(1, (frame - start) / ramp));
  const exit = Math.max(0, Math.min(1, (end - 1 - frame) / ramp));
  const value = Math.min(enter, exit);
  return value * value * (3 - 2 * value);
}

/** Who is speaking in a scene: the name card belongs to a speaker's whole turn, not to each scene. */
export type Speaker = "presenter" | "founder" | null;
export function speakerOf(type: string): Speaker {
  return type === "anchor" || type === "question" ? "presenter" : type === "answer" ? "founder" : null;
}
/** Per scene: does a speaker's turn START here? (The previous scene had someone else, or nobody, speaking.) */
export function turnStarts(types: string[]): boolean[] {
  return types.map((t, i) => speakerOf(t) !== null && speakerOf(t) !== (i > 0 ? speakerOf(types[i - 1]) : null));
}

/** Video Rulebook BIV-GFX-010: a card enters once when its speaker's turn starts, then stays fully on screen, still, to the
 *  last frame of the turn. A scene that continues the same speaker's turn shows it fully from its first frame (no re-entry),
 *  and nothing fades out while anyone is speaking: the card leaves with the cut to the next speaker. */
export function turnCard(frame: number, duration: number, fps: number, enters: boolean, delaySeconds = 0, rampSeconds = .4): number {
  if (!enters) return 1;
  const start = Math.min(delaySeconds * fps, Math.max(0, duration / 5));
  const ramp = Math.max(1, Math.min(fps * rampSeconds, (duration - start) / 3));
  const v = Math.max(0, Math.min(1, (frame - start) / ramp));
  return v * v * (3 - 2 * v);
}
