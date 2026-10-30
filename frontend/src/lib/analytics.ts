export type PlatformMetric = "impressions" | "story_visits" | "share_visits" | "video_views" | "video_completions";
export const metricLabels: Record<PlatformMetric, string> = { impressions: "Story impressions", story_visits: "Story visits", share_visits: "Shared-video visits", video_views: "Engaged video views", video_completions: "Video completions" };
export type Snapshot = { id: string; placement_id: string; as_of: string; views: number | null; impressions: number | null; source_note: string; updated_at: string; updated_by?: string };
export type ChannelAnalytics = { placement_id: string; request_id: string; project_id: string | null; outlet: string; headline: string; company: string; status: string; published_url: string; views: number | null; impressions: number | null; views_as_of: string | null; impressions_as_of: string | null; history: Snapshot[] };
export type AudienceReport = { start: string; end: string; timezone: string; platform: Record<PlatformMetric, number>; series: ({ date: string } & Record<PlatformMetric, number>)[]; first_recorded_activity: string | null; legacy_share_opens_lifetime: number; projects: ({ id: string; title: string; company: string } & Record<PlatformMetric, number>)[]; channels: ChannelAnalytics[]; channel_totals: { views: number | null; impressions: number | null; outlets: number; outlets_with_reports: number }; definitions: Record<string, string> };
export async function analyticsRequest<T>(path: string, token: string | null, method = "GET", body?: unknown): Promise<T> {
  const r = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/${path}`, { method, headers: { Authorization: `Bearer ${token ?? ""}`, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const value = await r.json();
  if (!r.ok) throw new Error(typeof value.detail === "string" ? value.detail : Array.isArray(value.detail) ? value.detail.map((e: { msg?: string }) => e.msg).join("; ") : "Unable to load analytics. Please try again.");
  return value as T;
}
export async function downloadReport(path: string, token: string | null) {
  const response = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/${path}`, { headers: { Authorization: `Bearer ${token ?? ""}` } });
  if (!response.ok) throw new Error("Unable to download the report. Check the date range and try again.");
  const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = "cover-founder-audience-report.csv"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const utcDate = (offset = 0) => { const d = new Date(); d.setUTCDate(d.getUTCDate() + offset); return d.toISOString().slice(0, 10); };
