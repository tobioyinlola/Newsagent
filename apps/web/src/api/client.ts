import createClient, { type Middleware } from "openapi-fetch";
import { getToken } from "../lib/auth";
import type { components, paths } from "./schema";

const auth: Middleware = {
  onRequest({ request }) {
    const t = getToken();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: import.meta.env.VITE_API_URL ?? "" });
api.use(auth);

export type Schemas = components["schemas"];

export class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

// Turns openapi-fetch's {data,error,response} into data-or-throw with a human message.
export async function unwrap<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (response.ok && data !== undefined) return data;
  if (response.ok) return undefined as T;
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  let message = response.statusText || "Something went wrong";
  if (typeof detail === "string") message = detail;
  else if (detail && typeof detail === "object" && "error" in detail) message = String((detail as { error: unknown }).error);
  if (response.status === 401) message = "Please sign in again.";
  throw new ApiError(response.status, message, detail);
}
