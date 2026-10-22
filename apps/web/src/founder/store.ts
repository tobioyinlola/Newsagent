// Local copy of recorded chunks. Kept until the server confirms the whole take, so a dropped connection or a
// reload never loses a recording. IndexedDB when available; an in-memory Map when it isn't (private browsing).
export type TakeMeta = { takeId: string; question: number; kind: "video" | "audio"; mime: string };

const DB = "newsagent-founder";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore("chunks", { keyPath: ["takeId", "idx"] }).createIndex("take", "takeId");
      req.result.createObjectStore("meta", { keyPath: "takeId" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function tx<T>(db: IDBDatabase, store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const r = fn(db.transaction(store, mode).objectStore(store));
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

export class ChunkStore {
  private mem = new Map<string, Blob>();
  private metas = new Map<string, TakeMeta>();
  private db: Promise<IDBDatabase | null>;

  constructor() {
    this.db = typeof indexedDB === "undefined" ? Promise.resolve(null) : open().catch(() => null);
  }
  private key = (t: string, i: number) => `${t}:${i}`;

  async put(takeId: string, idx: number, blob: Blob) {
    this.mem.set(this.key(takeId, idx), blob);
    const db = await this.db;
    if (db) await tx(db, "chunks", "readwrite", (s) => s.put({ takeId, idx, blob })).catch(() => undefined);
  }
  async get(takeId: string, idx: number): Promise<Blob | undefined> {
    const m = this.mem.get(this.key(takeId, idx));
    if (m) return m;
    const db = await this.db;
    if (!db) return undefined;
    const r = (await tx(db, "chunks", "readonly", (s) => s.get([takeId, idx])).catch(() => undefined)) as { blob: Blob } | undefined;
    return r?.blob;
  }
  async indexes(takeId: string): Promise<number[]> {
    const out = new Set<number>([...this.mem.keys()].filter((k) => k.startsWith(`${takeId}:`)).map((k) => Number(k.split(":")[1])));
    const db = await this.db;
    if (db) {
      const rows = (await tx(db, "chunks", "readonly", (s) => s.index("take").getAll(takeId)).catch(() => [])) as { idx: number }[];
      rows.forEach((r) => out.add(r.idx));
    }
    return [...out].sort((a, b) => a - b);
  }
  async delete(takeId: string, idx: number) {
    this.mem.delete(this.key(takeId, idx));
    const db = await this.db;
    if (db) await tx(db, "chunks", "readwrite", (s) => s.delete([takeId, idx])).catch(() => undefined);
  }
  async deleteTake(takeId: string) {
    for (const i of await this.indexes(takeId)) await this.delete(takeId, i);
    this.metas.delete(takeId);
    const db = await this.db;
    if (db) await tx(db, "meta", "readwrite", (s) => s.delete(takeId)).catch(() => undefined);
  }
  async setMeta(m: TakeMeta) {
    this.metas.set(m.takeId, m);
    const db = await this.db;
    if (db) await tx(db, "meta", "readwrite", (s) => s.put(m)).catch(() => undefined);
  }
  async allMeta(): Promise<TakeMeta[]> {
    const db = await this.db;
    const rows = db ? ((await tx(db, "meta", "readonly", (s) => s.getAll()).catch(() => [])) as TakeMeta[]) : [];
    return rows.length ? rows : [...this.metas.values()];
  }
}
