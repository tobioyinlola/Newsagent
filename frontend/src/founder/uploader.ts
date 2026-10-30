import { guest, must } from "./guestApi";
import type { ChunkStore } from "./store";

export type UploadState = { confirmed: number; pending: number; online: boolean; lastError: string | null };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Sends a take's chunks straight to storage with presigned URLs, confirming each with the server.
// Resumable by design: the server's list of confirmed chunks is the truth, and the local copy is kept until
// the whole take is confirmed. Retries with backoff and wakes immediately when the connection returns.
export class TakeUploader {
  private confirmed = new Set<number>();
  private known = new Set<number>(); // chunks we hold locally
  private running = false;
  private stopped = false;
  private wake: (() => void) | null = null;
  private lastError: string | null = null;
  private fatalError: Error | null = null;

  constructor(private token: string, readonly takeId: string, private store: ChunkStore, private onChange: (s: UploadState) => void) {
    window.addEventListener("online", this.poke);
  }

  private poke = () => this.wake?.();
  dispose() { this.stopped = true; window.removeEventListener("online", this.poke); this.poke(); }

  state(): UploadState {
    const pending = [...this.known].filter((i) => !this.confirmed.has(i)).length;
    return { confirmed: this.confirmed.size, pending, online: navigator.onLine, lastError: this.lastError };
  }
  private emit() { this.onChange(this.state()); }

  async add(idx: number, blob: Blob) {
    await this.store.put(this.takeId, idx, blob);
    this.known.add(idx);
    this.emit();
    void this.pump();
  }

  // After a reload or reconnect: learn what the server already has, then continue with the rest.
  async resume() {
    for (const i of await this.store.indexes(this.takeId)) this.known.add(i);
    await this.syncFromServer();
    this.emit();
    void this.pump();
  }

  async syncFromServer() {
    const t = await must(guest.GET("/v1/interview/{token}/takes/{take_id}", { params: { path: { token: this.token, take_id: this.takeId } } }));
    t.chunks_received.forEach((i) => { this.confirmed.add(i); this.known.add(i); });
  }

  private async pump() {
    if (this.running) return;
    this.running = true;
    let backoff = 1000;
    try {
      while (!this.stopped) {
        const todo = [...this.known].filter((i) => !this.confirmed.has(i)).sort((a, b) => a - b).slice(0, 4);
        if (!todo.length) break;
        try {
          if (!navigator.onLine) throw new Error("offline");
          const { urls } = await must(guest.POST("/v1/interview/{token}/takes/{take_id}/chunk-urls", { params: { path: { token: this.token, take_id: this.takeId } }, body: { indexes: todo } }));
          await Promise.all(todo.map((i) => this.sendOne(i, urls[String(i)])));
          this.lastError = null;
          backoff = 1000;
        } catch (e) {
          if ([400, 401, 403, 404, 410, 413, 415, 422].includes((e as { status?: number }).status ?? 0) || ((e as { status?: number }).status === 409 && (e as Error).message.includes("already finished"))) { this.fatalError = e as Error; this.lastError = (e as Error).message; break; } // link gone / take finished
          this.lastError = (e as Error).message;
          this.emit();
          await Promise.race([sleep(backoff), new Promise<void>((r) => { this.wake = r; })]);
          this.wake = null;
          backoff = Math.min(backoff * 2, 15000);
        }
        this.emit();
      }
    } finally {
      this.running = false;
      this.emit();
    }
  }

  private async sendOne(idx: number, url: string) {
    const blob = await this.store.get(this.takeId, idx);
    if (!blob) throw new Error("local chunk missing");
    const put = await fetch(url, { method: "PUT", body: blob });
    if (!put.ok) throw new Error(`upload failed (${put.status})`);
    await must(guest.POST("/v1/interview/{token}/takes/{take_id}/chunks/{idx}/confirm", { params: { path: { token: this.token, take_id: this.takeId, idx } } }));
    this.confirmed.add(idx);
    this.emit();
  }

  // Resolves once every chunk in [0, count) is confirmed. Rejects if the uploader is stopped first.
  async drained(count: number, onWait?: (s: UploadState) => void): Promise<void> {
    for (;;) {
      if (this.stopped) throw new Error("stopped");
      if (this.fatalError) throw this.fatalError;
      if ([...Array(count).keys()].every((i) => this.confirmed.has(i))) return;
      onWait?.(this.state());
      void this.pump();
      await sleep(400);
    }
  }

  // Reconcile against the server before finishing, including older confirmations lost by a race.
  async complete(count: number, onWait?: (s: UploadState) => void) {
    for (let attempt = 0; ; attempt++) {
      await this.drained(count, onWait);
      try {
        return await must(guest.POST("/v1/interview/{token}/takes/{take_id}/complete", { params: { path: { token: this.token, take_id: this.takeId } }, body: { chunk_count: count } }));
      } catch (e) {
        const detail = (e as { detail?: { error?: string; missing?: unknown } }).detail;
        if ((e as { status?: number }).status !== 409 || detail?.error !== "missing_chunks" || !Array.isArray(detail.missing) || !detail.missing.length || attempt >= 3) throw e;
        for (const index of detail.missing) {
          if (!Number.isInteger(index) || index < 0 || index >= count) throw e;
          if (!await this.store.get(this.takeId, index)) throw new Error("Part of this recording is unavailable on this device. Please record this answer again.");
          this.confirmed.delete(index); this.known.add(index);
        }
        this.emit();
      }
    }
  }

  async clearLocal() { await this.store.deleteTake(this.takeId); }
}
