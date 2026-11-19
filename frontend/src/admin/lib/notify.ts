// One place that tells the back office "that worked". Every successful change made from the back office (a save, an
// approval, a removal) pops a short message, so nobody has to wonder whether it went through.
type Listener = (message: string) => void;
const listeners = new Set<Listener>();
export const subscribe = (fn: Listener) => { listeners.add(fn); return () => { listeners.delete(fn); }; };
export const notify = (message: string) => listeners.forEach((fn) => fn(message));

// Requests that change nothing worth announcing: signing in, previews, test sends, drafts, looking at details, usage measuring.
const QUIET = /\/v1\/(auth\/|dev\/)|\/(preview|test|test-send|draft|reveal|account-details|search|export|event|logout|otp|resend)(\/|\?|$)|\/mailbox\/test/;
const WRITES: Record<string, string> = { PUT: "Saved", PATCH: "Saved", POST: "Saved", DELETE: "Removed" };

/** The message for a finished request, or null when nothing should be announced. */
export function messageFor(method: string, url: string, ok: boolean): string | null {
  const text = WRITES[method.toUpperCase()];
  if (!ok || !text) return null;
  let path = url;
  try { path = new URL(url, window.location.origin).pathname; } catch { /* keep the raw text */ }
  if (!path.startsWith("/v1/") && !/\/v1\//.test(url)) return null; // only our own API, never a file upload to storage
  return QUIET.test(path) ? null : text;
}

let installed = false;
/** Watches the back office's own requests once. Safe to call again. */
export function announceSaves() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const response = await original(input, init);
    try {
      const method = init?.method ?? (input instanceof Request ? input.method : "GET");
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const text = messageFor(method, url, response.ok);
      if (text) notify(text);
    } catch { /* announcing must never break a save */ }
    return response;
  };
}
