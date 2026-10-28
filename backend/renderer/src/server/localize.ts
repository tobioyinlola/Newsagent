import fs from "node:fs";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

const PARALLEL = 4;

/** A copy of `props` in which every remote http(s) link is replaced by a file downloaded into `dir`, served at `urlFor(file)`.
 * The same link is downloaded once however often it appears. A download that fails throws, so the render fails with the reason. */
export async function localizeMedia<T>(props: T, dir: string, urlFor: (file: string) => string, fetchFn: typeof fetch = fetch): Promise<T> {
  fs.mkdirSync(dir, { recursive: true });
  const links = new Map<string, string>();
  const walk = (v: unknown): void => {
    if (typeof v === "string") {
      if (/^https?:\/\//i.test(v) && !/^https?:\/\/(127\.0\.0\.1|localhost)[:/]/i.test(v) && !links.has(v)) {
        const ext = (new URL(v).pathname.match(/\.([a-z0-9]{2,5})$/i)?.[1] ?? "bin").toLowerCase();
        links.set(v, `${links.size}.${ext}`);
      }
    } else if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") Object.values(v).forEach(walk);
  };
  walk(props);
  const todo = [...links.entries()];
  const worker = async () => {
    for (let next = todo.shift(); next; next = todo.shift()) {
      const [link, file] = next;
      const r = await fetchFn(link);
      if (!r.ok || !r.body) throw new Error(`could not download a video file for the render (${r.status})`);
      await pipeline(Readable.fromWeb(r.body as never), fs.createWriteStream(path.join(dir, file)));
    }
  };
  await Promise.all(Array.from({ length: Math.min(PARALLEL, todo.length) }, worker));
  const swap = (v: unknown): unknown => {
    if (typeof v === "string") return links.has(v) ? urlFor(links.get(v)!) : v;
    if (Array.isArray(v)) return v.map(swap);
    if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, swap(x)]));
    return v;
  };
  return swap(props) as T;
}
