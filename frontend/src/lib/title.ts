// A video is named after its business and the moment it was made: "Onyeka & Sons Ltd · Oct 29, 2026, 10:42 AM".
export function videoTitle(company: string | undefined, createdAt: string): string {
  const d = new Date(createdAt);
  const stamp = d.toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
  return company ? `${company} · ${stamp}` : stamp;
}
