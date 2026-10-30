import { ApiError } from "../api/client";

export type Outlet = { id: string; name: string; credits: string; region: string };
export type Draft = { stage: string; outlet_ids: string[]; project_id: string | null; story_project_id?: string | null; announcement_source?: "platform" | "custom"; headline: string; announcement: string; contact_name: string; contact_email: string; phone: string; whatsapp: string; logo_key: string; picture_keys: string[] };
export type Distribution = { id: string; workspace_id: string; created_by: string; status: string; stage: string; data: Draft & { outlets?: Outlet[] }; total_credits: string; paid: boolean; email_sent: boolean; created_at: string; updated_at: string; submitted_at: string | null };
export async function distributionApi<T>(path: string, token: string | null, method = "GET", body?: unknown): Promise<T> {
  const r = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/${path}`, { method, headers: { Authorization: `Bearer ${token ?? ""}`, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await r.json();
  if (!r.ok) throw new ApiError(r.status, typeof data.detail === "string" ? data.detail : data.detail?.message ?? "Unable to save distribution request. Please try again.", data.detail);
  return data as T;
}
