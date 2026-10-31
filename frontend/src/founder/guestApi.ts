import createClient from "openapi-fetch";
import type { components, paths } from "../api/schema";

// The founder has no account, so this client never sends an Authorization header.
export const guest = createClient<paths>({ baseUrl: import.meta.env.VITE_API_URL ?? "" });
export type GuestView = components["schemas"]["GuestView"];
export type GuestTake = components["schemas"]["GuestTake"];
export type GuestQuestion = components["schemas"]["GuestQuestion"];

export async function must<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (response.ok) return data as T;
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  const message =
    typeof detail === "string" ? detail : detail && typeof detail === "object" && "message" in detail ? String((detail as { message: unknown }).message) : "Something went wrong. Please try again.";
  throw Object.assign(new Error(message), { status: response.status, detail });
}

// Chunks are ~2 s each. 80 chunks is the server's cap; recordings stop at 2 minutes.
export const CHUNK_MS = 2000;
export const HARD_CAP_S = 65; // 60 seconds plus 5 seconds to round up
