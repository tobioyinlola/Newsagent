import createClient, { type Middleware } from "openapi-fetch";
import { getToken, setToken } from "../lib/auth";
import type { components, paths } from "../../api/schema";
import { type Paged, totalOf } from "../../lib/paging";

// The browser's own "Failed to fetch" means the server couldn't be reached at all (offline, a deploy in progress, a blocked
// request). Say that in plain words instead.
const reachable: typeof fetch = async (input, init) => {
  try {
    return await fetch(input, init);
  } catch (e) {
    if (e instanceof TypeError) throw new Error("We couldn't reach the server. Check your connection and try again.");
    throw e;
  }
};

const auth: Middleware = {
  onRequest({ request }) {
    const t = getToken();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: import.meta.env.VITE_API_URL ?? "", fetch: reachable });
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
  // an answer with no explanation: say who answered and what, so a wrong address or a proxy error is obvious
  const where = (() => { try { const u = new URL(response.url); return `${u.host}${u.pathname}`; } catch { return response.url; } })();
  let message = response.statusText || `Something went wrong (${response.status} from ${where})`;
  if (typeof detail === "string") message = detail;
  else if (detail && typeof detail === "object" && "message" in detail) message = String((detail as { message: unknown }).message);
  else if (detail && typeof detail === "object" && "error" in detail) message = String((detail as { error: unknown }).error);
  const signingIn = /\/v1\/auth\/(login|signup|password)/.test(response.url);
  if (response.status === 401 && !signingIn) {
    message = "Please sign in again.";
    const otp = (detail as { error?: string } | undefined)?.error === "otp_required";
    // expired (e.g. an hour idle) or revoked: clear the dead token and go to sign-in
    if (!otp && getToken() && !location.pathname.startsWith("/admin/login")) {
      setToken(null);
      location.assign("/admin/login?expired=1"); // the back office lives under /admin
    }
  }
  throw new ApiError(response.status, message, detail);
}

/** A list with its total: an array reply (total in the X-Total-Count header) or an object (total beside the items; `pick` finds the rows). */
export async function unwrapPage<D extends unknown[]>(p: Promise<{ data?: D; error?: unknown; response: Response }>, pick?: undefined, offset?: number): Promise<Paged<D[number]>>;
export async function unwrapPage<T>(p: Promise<{ data?: unknown; error?: unknown; response: Response }>, pick: (body: any) => T[], offset?: number): Promise<Paged<T>>; // eslint-disable-line @typescript-eslint/no-explicit-any
export async function unwrapPage(
  p: Promise<{ data?: unknown; error?: unknown; response: Response }>,
  pick?: (body: any) => unknown[], // eslint-disable-line @typescript-eslint/no-explicit-any
  offset = 0,
): Promise<Paged<unknown>> {
  const res = await p;
  const data = (await unwrap(Promise.resolve(res as never))) as unknown;
  const items = (pick ? pick(data) : (data as unknown[] | undefined)) ?? [];
  return { items, total: totalOf(res.response.headers, data, items.length, offset) };
}
