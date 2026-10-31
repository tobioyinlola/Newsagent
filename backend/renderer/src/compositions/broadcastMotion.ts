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
