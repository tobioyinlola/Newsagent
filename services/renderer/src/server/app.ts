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

type Job = { status: "queued" | "running" | "succeeded" | "failed"; progress: number; output_keys: string[]; error: string | null; result?: unknown };
type Output = { kind?: "video" | "thumbnail"; name?: string; scale?: number; format: "16x9" | "9x16"; width: number; height: number };

export function createApp(opts: { maxQueue?: number; secret: string; maxConcurrent?: number; processFn?: typeof processTake; keyFn?: typeof chromaKey; renderFn?: typeof renderOne; thumbFn?: typeof renderThumbnail; analyzeFn?: (url: string) => Promise<Analysis>; normalizeFn?: (file: string) => Promise<void> }) {
  const app = express();
  app.use(express.json({ limit: "1mb" }));
  const jobs = new Map<string, Job>();
  const queue: (() => Promise<void>)[] = [];
  let running = 0;
  const max = opts.maxConcurrent ?? Number(process.env.RENDER_JOBS_CONCURRENCY || 1);
  const maxQueue = opts.maxQueue ?? Number(process.env.MAX_QUEUE || 20);
  const render = opts.renderFn ?? renderOne;
  const renderThumb = opts.thumbFn ?? renderThumbnail;
  const analyze = opts.analyzeFn ?? analyzeUrl;
  const processFile = opts.processFn ?? processTake;
  const keyOut = opts.keyFn ?? chromaKey;
  const normalize = opts.normalizeFn ?? normalizeAudio;

  const pump = () => {
    while (running < max && queue.length) {
      const next = queue.shift()!;
      running++;
      next().finally(() => { running--; pump(); });
    }
  };

  app.get("/health", (_req, res) => res.json({ status: "ok", queued: queue.length, running }));

  app.use((req, res, next) => {
    const given = Buffer.from(String(req.header("x-renderer-secret") || ""));
    const want = Buffer.from(opts.secret);
    if (!opts.secret || given.length !== want.length || !crypto.timingSafeEqual(given, want)) {
      return res.status(401).json({ error: "unauthorized" });
    }
    next();
  });

  // Back-pressure: when the waiting line is full, say so (429 + Retry-After) rather than queueing without bound.
  const busy = (_req: express.Request, res: express.Response, next: express.NextFunction) => {
    if (queue.length >= maxQueue) {
      res.set("Retry-After", String(Math.min(60, 5 + queue.length * 2)));
      return res.status(429).json({ error: "renderer busy", queued: queue.length });
    }
    next();
  };
  app.post("/renders", busy, (req, res) => {
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
    queue.push(async () => {
      job.status = "running";
      const dir = fs.mkdtempSync(path.join(os.tmpdir(), "render-"));
      try {
        for (const [i, o] of outputs.entries()) {
          const thumb = o.kind === "thumbnail";
          const base = o.name ?? o.format;
          if (!/^[a-z0-9x_-]+$/i.test(base)) throw new Error("invalid output name");
          const file = path.join(dir, `${base}.${thumb ? "png" : "mp4"}`);
          if (thumb) await renderThumb(o.format, merged, file, composition);
          else {
            assertEvenScale(o.width, o.height, o.scale ?? 1);
            await render({ composition, format: o.format, props: merged, outFile: file, scale: o.scale, onProgress: (p) => { job.progress = (i + p) / outputs.length; } });
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
        fs.rmSync(dir, { recursive: true, force: true });
      }
    });
    pump();
    res.status(202).json({ render_id: id });
  });

  // Founder takes: concatenate uploaded chunks, clean up, trim, flag problems, upload results.
  app.post("/process", busy, (req, res) => {
    const { chunk_urls, kind, ext, output_prefix } = req.body as { chunk_urls: string[]; kind: "video" | "audio"; ext: string; output_prefix: string };
    if (!Array.isArray(chunk_urls) || !chunk_urls.length || chunk_urls.length > 400 || !["video", "audio"].includes(kind) || !output_prefix || output_prefix.includes("..") || !/^[a-z0-9]{2,5}$/i.test(ext ?? "")) {
      return res.status(400).json({ error: "invalid request" });
    }
    const id = crypto.randomUUID();
    const job: Job = { status: "queued", progress: 0, output_keys: [], error: null };
    jobs.set(id, job);
    queue.push(async () => {
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
    pump();
    res.status(202).json({ render_id: id });
  });

  // Green-screen avatar video -> transparent WebM, uploaded to output_key.
  app.post("/chromakey", busy, (req, res) => {
    const { url, output_key, color, similarity, blend } = req.body as { url: string; output_key: string; color?: string; similarity?: number; blend?: number };
    if (!url || !output_key || output_key.includes("..") || !output_key.endsWith(".webm")) return res.status(400).json({ error: "invalid request" });
    const id = crypto.randomUUID();
    const job: Job = { status: "queued", progress: 0, output_keys: [], error: null };
    jobs.set(id, job);
    queue.push(async () => {
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
    pump();
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

  app.get("/renders/:id", (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job) return res.status(404).json({ error: "not found" });
    res.json(job);
  });

  return app;
}
