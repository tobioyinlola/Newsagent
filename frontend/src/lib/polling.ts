/** How long to wait before asking the server again. Quick while someone has just opened a page and is watching it change, then slower
 *  the longer it stays open: a video takes minutes to make, so a page that has been open for two minutes does not need to ask every
 *  few seconds. Thousands of open pages asking every 4 seconds is a steady load on the one API process for no visible gain. */
export function backoffInterval(openedAt: number, fastMs: number, now: number = Date.now()): number {
  const open = now - openedAt;
  if (open < 30_000) return fastMs;
  if (open < 120_000) return Math.max(fastMs, 10_000);
  return Math.max(fastMs, 20_000);
}
