import { getToken } from "./auth";

export type ProjectEvent = { state: string; failure_reason: string | null; cost_total: string };
const TERMINAL = new Set(["final_ready", "failed", "limit_reached", "cancelled"]);

function reconnectDelay(signal: AbortSignal) {
  return new Promise<void>(resolve => {
    if (signal.aborted) { resolve(); return; }
    const finish = () => { clearTimeout(timer); signal.removeEventListener("abort", finish); resolve(); };
    const timer = setTimeout(finish, 3000);
    signal.addEventListener("abort", finish, { once: true });
  });
}

// Fetch supports our auth header. Normal EOF may be a server/proxy timeout, not a finished video.
export async function streamProjectEvents(projectId: string, onEvent: (e: ProjectEvent) => void, signal: AbortSignal) {
  while (!signal.aborted) {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/projects/${projectId}/events`, {
        headers: { Authorization: `Bearer ${getToken() ?? ""}` }, signal,
      });
      if (!res.ok || !res.body) throw new Error(String(res.status));
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
      try {
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += value;
          let i: number;
          while ((i = buf.indexOf("\n\n")) >= 0) {
            const block = buf.slice(0, i);
            buf = buf.slice(i + 2);
            const data = block.split("\n").find(l => l.startsWith("data: "));
            if (data) {
              const event: ProjectEvent = JSON.parse(data.slice(6));
              onEvent(event);
              if (TERMINAL.has(event.state)) return;
            }
          }
        }
      } finally { await reader.cancel().catch(() => undefined); reader.releaseLock(); }
    } catch {
      if (signal.aborted) return;
    }
    await reconnectDelay(signal);
  }
}
