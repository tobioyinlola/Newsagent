import { ApiError } from "../api/client";
import { type Paged, totalOf } from "./paging";

export type Outlet = { id: string; name: string; credits: string; region: string; country?: string | null; topic?: string; category?: string; media_policy_configured?: boolean; accepts_logo?: boolean; accepts_images?: boolean; logo_credits?: string; picture_credits?: string; base_credits?: string; logo_fee?: string; picture_fee?: string };
export type Draft = { stage: string; outlet_ids: string[]; project_id: string | null; story_project_id?: string | null; announcement_source?: "platform" | "custom"; headline: string; announcement: string; contact_name: string; contact_email: string; phone: string; whatsapp?: string; phone_country?: string; whatsapp_country?: string; logo_key: string; picture_keys: string[]; media_options?: Record<string, { include_logo: boolean; include_pictures: boolean }>; plan_key?: "" | "essential" | "balanced" | "max"; plan_ids?: string[] };
export type Distribution = { id: string; workspace_id: string; created_by: string; status: string; stage: string; data: Draft & { outlets?: Outlet[] }; total_credits: string; paid: boolean; email_sent: boolean; created_at: string; updated_at: string; submitted_at: string | null; invoice?: Invoice | null; placements?: Placement[]; emails?: DistributionEmail[]; activity?: { id: string; kind: string; actor: string; detail: Record<string, unknown>; created_at: string }[] };
async function distributionRaw(path: string, token: string | null, method = "GET", body?: unknown): Promise<{ data: unknown; headers: Headers }> {
  const r = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/${path}`, { method, headers: { Authorization: `Bearer ${token ?? ""}`, "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await r.json();
  if (!r.ok) throw new ApiError(r.status, typeof data.detail === "string" ? data.detail : Array.isArray(data.detail) ? data.detail.map((e: { msg?: string }) => e.msg ?? "Invalid field").join("; ") : data.detail?.message ?? "Unable to save distribution request. Please try again.", data.detail);
  return { data, headers: r.headers };
}
export async function distributionApi<T>(path: string, token: string | null, method = "GET", body?: unknown): Promise<T> {
  return (await distributionRaw(path, token, method, body)).data as T;
}
/** One page of a list, with the total. `pick` finds the rows when the reply is an object rather than an array. */
export async function distributionPage<T>(path: string, token: string | null, limit: number, offset: number, pick?: (body: any) => T[]): Promise<Paged<T>> { // eslint-disable-line @typescript-eslint/no-explicit-any
  const { data, headers } = await distributionRaw(`${path}${path.includes("?") ? "&" : "?"}limit=${limit}&offset=${offset}`, token);
  const items = ((pick ? pick(data) : data) as T[] | undefined) ?? [];
  return { items, total: totalOf(headers, data, items.length, offset) };
}

export type Invoice = { number: string; issued_at: string; payment_method: string; status: string; reference: string; total_credits: string; items: Outlet[] };
export type Placement = { id: string; outlet_id: string; name: string; status: "pending" | "in_progress" | "published"; credits: string; published_url: string; published_at: string | null; internal_status?: string; internal_notes?: string; contact_email?: string; outreach_subject?: string; outreach_body?: string };
export type DistributionEmail = { id: string; placement_id: string | null; kind: string; recipient: string; subject: string; body: string; status: string; attempts: number; error: string; created_at: string; sent_at: string | null };
export const distributionStatus = (status: string) => ({ submitted: "Pending", pending: "Pending", in_progress: "In progress", completed: "Published", published: "Published", draft: "Draft" }[status] ?? status);
export function priceOutlets(outlets: Outlet[], draft: Draft | null): Outlet[] {
  return outlets.filter(o => draft?.outlet_ids.includes(o.id)).map(o => {
    const choice = draft?.media_options?.[o.id];
    const logo = o.media_policy_configured !== false && !!draft?.logo_key && o.accepts_logo !== false && choice?.include_logo !== false;
    const pictures = o.media_policy_configured !== false && o.accepts_images !== false && choice?.include_pictures !== false ? draft?.picture_keys.length ?? 0 : 0;
    const logoFee = logo ? Number(o.logo_credits ?? 0) : 0;
    const pictureFee = pictures * Number(o.picture_credits ?? 0);
    return { ...o, base_credits: o.credits, logo_fee: String(logoFee), picture_fee: String(pictureFee), credits: String(Number((Number(o.credits) + logoFee + pictureFee).toFixed(4))) };
  });
}

/** What a new distribution request starts with when no video was chosen up front: the most recent story, ready to send
 *  (the owner can switch to their own text), plus that story's video if it has a finished one. Null when there are no stories. */
export function latestStoryStart(
  stories: { project_id: string; headline: string; announcement: string }[] | undefined,
  videos: { id: string }[] | undefined,
) {
  const latest = stories?.[0]; // the list arrives newest first
  if (!latest) return null;
  return {
    announcement_source: "platform" as const,
    story_project_id: latest.project_id,
    headline: latest.headline,
    announcement: latest.announcement,
    project_id: videos?.find((v) => v.id === latest.project_id)?.id ?? null,
  };
}
