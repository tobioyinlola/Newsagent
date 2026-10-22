import { getToken } from "./auth";

export type ProjectEvent = { state: string; failure_reason: string | null; cost_total: string };

// EventSource cannot send an Authorization header, so we stream with fetch. Reconnects until aborted.
export async function streamProjectEvents(projectId: string, onEvent: (e: ProjectEvent) => void, signal: AbortSignal) {
  while (!signal.aborted) {
    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/projects/${projectId}/events`, {
        headers: { Authorization: `Bearer ${getToken() ?? ""}` },
        signal,
      });
      if (!res.ok || !res.body) throw new Error(String(res.status));
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += value;
        let i: number;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, i);
          buf = buf.slice(i + 2);
          const data = block.split("\n").find((l) => l.startsWith("data: "));
          if (data) onEvent(JSON.parse(data.slice(6)));
        }
      }
      return; // server closes the stream at a terminal state
    } catch {
      if (signal.aborted) return;
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
}
