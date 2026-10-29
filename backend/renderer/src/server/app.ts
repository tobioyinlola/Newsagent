import { makeCancelSignal } from "@remotion/renderer";
import express from "express";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { NewsProps, defaultProps } from "../compositions/types";
import { assertEvenScale, compositionName, renderOne, renderThumbnail } from "../render";
import { Analysis, analyzeUrl, normalizeAudio } from "../media";
import { chromaKey } from "../chromakey";
import { processTake } from "../process";
import { putFile } from "./storage";
import { localizeMedia } from "./localize";

type Job = { status: "queued" | "running" | "succeeded" | "failed"; progress: number; output_keys: string[]; error: string | null; result?: unknown; cancel?: () => void; cancelled?: boolean; endedAt?: number };
type Output = { kind?: "video" | "thumbnail"; name?: string; scale?: number; format: "16x9" | "9x16"; width: number; height: number };

export function createApp(opts: { maxQueue?: number; secret: string; maxConcurrent?: number; maxLight?: number; jobTtlMs?: number; processFn?: typeof processTake; keyFn?: typeof chromaKey; renderFn?: typeof renderOne; thumbFn?: typeof renderThumbnail; analyzeFn?: (url: string) => Promise<Analysis>; normalizeFn?: (file: string) => Promise<void> }) {
  const app = express();
  app.use(express.json({ limit: "1mb" }));
  const jobs = new Map<string, Job>();
  // Two lines, so a founder's recording is processed within seconds even while a long render is under way: renders (heavy, few
  // at a time) and everything quick (recording clean-up, green-screen removal).
  type Lane = { queue: (() => Promise<void>)[]; running: number; max: number };
  const heavy: Lane = { queue: [], running: 0, max: opts.maxConcurrent ?? Number(process.env.RENDER_JOBS_CONCURRENCY || 1) };
  const light: Lane = { queue: [], running: 0, max: opts.maxLight ?? Number(process.env.RENDER_LIGHT_CONCURRENCY || 2) };
  const maxQueue = opts.maxQueue ?? Number(process.env.MAX_QUEUE || 20);
  const render = opts.renderFn ?? renderOne;
  const renderThumb = opts.thumbFn ?? renderThumbnail;
  const analyze = opts.analyzeFn ?? analyzeUrl;
  const processFile = opts.processFn ?? processTake;
  const keyOut = opts.keyFn ?? chromaKey;
  const normalize = opts.normalizeFn ?? normalizeAudio;

  const pump = (lane: Lane) => {
    while (lane.running < lane.max && lane.queue.length) {
      const next = lane.queue.shift()!;
      lane.running++;
      next().finally(() => { lane.running--; pump(lane); });
    }
  };
  const enqueue = (lane: Lane, work: () => Promise<void>) => { lane.queue.push(work); pump(lane); };

  // Finished jobs are kept for a while so they can be polled, then forgotten: the map must not grow for ever.
  const jobTtl = opts.jobTtlMs ?? 3600_000;
  const sweepJobs = setInterval(() => {
    const now = Date.now();
    for (const [id, j] of jobs) {
      if (j.status === "succeeded" || j.status === "failed") {
        j.endedAt ??= now;
        if (now - j.endedAt > jobTtl) jobs.delete(id);
      }
    }
  }, 60_000);
  sweepJobs.unref();

  app.get("/health", (_req, res) => res.json({ status: "ok", queued: heavy.queue.length + light.queue.length, running: heavy.running + light.running, render: { queued: heavy.queue.length, running: heavy.running }, quick: { queued: light.queue.length, running: light.running } }));

  // Media for a render in progress, downloaded beforehand (see localize.ts). Served to the render's own browser on this
  // machine only; the folder name is a random render id and is deleted when the render ends.
  const mediaDirs = new Map<string, string>();
  app.get("/media/:id/:file", (req, res) => {
    const dir = mediaDirs.get(req.params.id);
    if (!dir || !/^[0-9]+\.[a-z0-9]{2,5}$/.test(req.params.file)) return res.status(404).end();
    res.sendFile(path.join(dir, req.params.file));
  });

  app.use((req, res, next) => {
    const given = Buffer.from(String(req.header("x-renderer-secret") || ""));
    const want = Buffer.from(opts.secret);
    if (!opts.secret || given.length !== want.length || !crypto.timingSafeEqual(given, want)) {
      return res.status(401).json({ error: "unauthorized" });
    }
    next();
  });

  // Back-pressure: when the waiting line is full, say so (429 + Retry-After) rather than queueing without bound.
  const busyFor = (lane: Lane) => (_req: express.Request, res: express.Response, next: express.NextFunction) => {
    if (lane.queue.length >= maxQueue) {
      res.set("Retry-After", String(Math.min(60, 5 + lane.queue.length * 2)));
      return res.status(429).json({ error: "renderer busy", queued: lane.queue.length });
    }
    next();
  };
  app.post("/renders", busyFor(heavy), (req, res) => {
    const { composition, props, outputs, input_urls, output_prefix } = req.body as {
      composition: string; props: Partial<NewsProps>; outputs: Output[]; input_urls?: Record<string, string>; output_prefix: string;
    };
    if (!Array.isArray(outputs) || !outputs.length || !output_prefix || output_prefix.includes("..")) {
      return res.status(400).json({ error: "invalid request" });
    }
    const id = crypto.randomUUID();
    const job: Job = { status: "queued", progress: 0, output_keys: [], error: null };
    jobs.set(id, job);
    try { compositionName(composition); } catch { return res.status(400).json({ error: "unknown composition" }); }
    // NewsStudio takes the anchor from input_urls; InterviewMerge receives every URL inside props.scenes.
    const merged = composition === "InterviewMerge"
      ? (props as Record<string, unknown>)
      : ({ ...defaultProps, ...props, anchorSrc: input_urls?.anchor ?? props.anchorSrc ?? null } as NewsProps);
    const { cancelSignal, cancel } = makeCancelSignal();
    job.cancel = cancel;
    enqueue(heavy, async () => {
      if (job.cancelled) return; // stopped while it was waiting in line
      job.status = "running";
      const dir = fs.mkdtempSync(path.join(os.tmpdir(), "render-"));
      try {
        // Download every remote file first: links signed for minutes can expire during a long render (403), and reading
        // from disk is far faster than streaming each frame's source over the network.
        const mediaDir = path.join(dir, "media");
        mediaDirs.set(id, mediaDir);
        const port = Number(process.env.PORT || 4000);
        const local = await localizeMedia(merged, mediaDir, (f) => `http://127.0.0.1:${port}/media/${id}/${f}`);
        for (const [i, o] of outputs.entries()) {
          const thumb = o.kind === "thumbnail";
          const base = o.name ?? o.format;
          if (!/^[a-z0-9x_-]+$/i.test(base)) throw new Error("invalid output name");
          const file = path.join(dir, `${base}.${thumb ? "png" : "mp4"}`);
          if (thumb) await renderThumb(o.format, local, file, composition);
          else {
            assertEvenScale(o.width, o.height, o.scale ?? 1);
            if (job.cancelled) throw new Error("cancelled");
            await render({ composition, format: o.format, props: local, outFile: file, scale: o.scale, cancelSignal, onProgress: (p) => { job.progress = (i + p) / outputs.length; } });
          }
          if (!thumb && o.name !== "preview") await normalize(file); // preview skips the extra pass
          const key = `${output_prefix}/${base}.${thumb ? "png" : "mp4"}`;
          await putFile(key, file);
          job.output_keys.push(key);
        }
        job.status = "succeeded";
        job.progress = 1;
      } catch (e) {
        job.status = "failed";
        job.error = String((e as Error).message).slice(0, 500);
      } finally {
        mediaDirs.delete(id);
        fs.rmSync(dir, { recursive: true, force: true });
      }
    });
    res.status(202).json({ render_id: id });
  });

  // Founder takes: concatenate uploaded chunks, clean up, trim, flag problems, upload results.
  app.post("/process", busyFor(light), (req, res) => {
    const { chunk_urls, kind, ext, output_prefix } = req.body as { chunk_urls: string[]; kind: "video" | "audio"; ext: string; output_prefix: string };
    if (!Array.isArray(chunk_urls) || !chunk_urls.length || chunk_urls.length > 400 || !["video", "audio"].includes(kind) || !output_prefix || output_prefix.includes("..") || !/^[a-z0-9]{2,5}$/i.test(ext ?? "")) {
      return res.status(400).json({ error: "invalid request" });
    }
    const id = crypto.randomUUID();
    const job: Job = { status: "queued", progress: 0, output_keys: [], error: null };
    jobs.set(id, job);
    enqueue(light, async () => {
      job.status = "running";
      let dir: string | null = null;
      try {
        const r = await processFile({ chunkUrls: chunk_urls, kind, ext });
        dir = r.dir;
        const keys: Record<string, string | null> = { video_key: null, audio_key: `${output_prefix}/answer.mp3` };
        if (r.video_path) { keys.video_key = `${output_prefix}/answer.mp4`; await putFile(keys.video_key, r.video_path); job.output_keys.push(keys.video_key); }
        await putFile(keys.audio_key!, r.audio_path); job.output_keys.push(keys.audio_key!);
        job.result = { ...keys, duration_s: r.duration_s, width: r.width, height: r.height, flags: r.flags, stats: r.stats };
        job.status = "succeeded"; job.progress = 1;
      } catch (e) {
        job.status = "failed"; job.error = String((e as Error).message).slice(0, 500);
      } finally {
        if (dir) fs.rmSync(dir, { recursive: true, force: true });
      }
    });
    res.status(202).json({ render_id: id });
  });

  // Green-screen avatar video -> transparent WebM, uploaded to output_key.
  app.post("/chromakey", busyFor(light), (req, res) => {
    const { url, output_key, color, similarity, blend } = req.body as { url: string; output_key: string; color?: string; similarity?: number; blend?: number };
    if (!url || !output_key || output_key.includes("..") || !output_key.endsWith(".webm")) return res.status(400).json({ error: "invalid request" });
    const id = crypto.randomUUID();
    const job: Job = { status: "queued", progress: 0, output_keys: [], error: null };
    jobs.set(id, job);
    enqueue(light, async () => {
      job.status = "running";
      let dir: string | null = null;
      try {
        const r = await keyOut({ url, color, similarity, blend });
        dir = r.dir;
        await putFile(output_key, r.path);
        job.output_keys.push(output_key);
        job.result = { key: output_key, duration_s: r.duration_s, width: r.width, height: r.height };
        job.status = "succeeded"; job.progress = 1;
      } catch (e) {
        job.status = "failed"; job.error = String((e as Error).message).slice(0, 500);
      } finally {
        if (dir) fs.rmSync(dir, { recursive: true, force: true });
      }
    });
    res.status(202).json({ render_id: id });
  });

  app.post("/analyze", async (req, res) => {
    try {
      const url = String(req.body?.url ?? "");
      res.json(await analyze(url));
    } catch (e) {
      res.status(422).json({ error: String((e as Error).message).slice(0, 300) });
    }
  });

  // Stop a render whose video was cancelled, so it doesn't hold the renderer (and delay everyone else) for nothing.
  app.delete("/renders/:id", (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job) return res.status(404).json({ error: "not found" });
    if (job.status === "queued" || job.status === "running") {
      job.cancelled = true;
      job.cancel?.();
      if (job.status === "queued") { job.status = "failed"; job.error = "cancelled"; }
    }
    res.json({ status: job.status });
  });

  app.get("/renders/:id", (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job) return res.status(404).json({ error: "not found" });
    res.json(job);
  });

  return app;
}
