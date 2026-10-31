import { afterEach, describe, expect, it, vi } from "vitest";
import { streamProjectEvents } from "./sse";

const event = (state: string) => new Response(`event: state\ndata: ${JSON.stringify({ state, failure_reason: null, cost_total: "0" })}\n\n`);
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("project status stream", () => {
  it("reconnects after a normal nonterminal close and receives the completed state", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValueOnce(event("merging")).mockResolvedValueOnce(event("final_ready"));
    vi.stubGlobal("fetch", fetch);
    const states: string[] = [];
    const done = streamProjectEvents("existing-project", e => states.push(e.state), new AbortController().signal);
    await vi.advanceTimersByTimeAsync(3000);
    await done;
    expect(states).toEqual(["merging", "final_ready"]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it.each(["final_ready", "failed", "limit_reached", "cancelled"])("stops reconnecting on confirmed %s", async state => {
    const fetch = vi.fn().mockResolvedValue(event(state));
    vi.stubGlobal("fetch", fetch);
    await streamProjectEvents("project", () => undefined, new AbortController().signal);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("cancels a pending reconnect when the user leaves the page", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValue(event("rendering_anchor"));
    vi.stubGlobal("fetch", fetch);
    const ctl = new AbortController();
    const done = streamProjectEvents("project", () => undefined, ctl.signal);
    await vi.advanceTimersByTimeAsync(0);
    ctl.abort();
    await done;
    await vi.advanceTimersByTimeAsync(10000);
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
