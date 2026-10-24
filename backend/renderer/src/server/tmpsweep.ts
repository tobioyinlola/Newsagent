import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// A crash skips the `finally` that removes a job's scratch directory. Remove ones nobody has touched for a while.
const PREFIXES = ["render-", "take-", "analyze-", "key-"];

export function sweepTemp(maxAgeMs = 6 * 3600 * 1000, dir = os.tmpdir(), now = Date.now()): number {
  let removed = 0;
  for (const name of fs.readdirSync(dir)) {
    if (!PREFIXES.some((p) => name.startsWith(p))) continue;
    const full = path.join(dir, name);
    try {
      const st = fs.statSync(full);
      if (st.isDirectory() && now - st.mtimeMs > maxAgeMs) { fs.rmSync(full, { recursive: true, force: true }); removed++; }
    } catch { /* gone already, or not ours to remove */ }
  }
  return removed;
}
