/** Advance the broadcast time within a recorded programme; preserve the date/zone label. */
export function broadcastClock(label: string, elapsedSeconds: number): string {
  return label.replace(/(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM)/i, (_, hour: string, minute: string, period: string) => {
    const base = (Number(hour) % 12 + (period.toUpperCase() === "PM" ? 12 : 0)) * 3600 + Number(minute) * 60;
    const seconds = ((base + Math.max(0, Math.floor(elapsedSeconds))) % 86400);
    const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
    return `${h % 12 || 12}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")} ${h >= 12 ? "PM" : "AM"}`;
  });
}
