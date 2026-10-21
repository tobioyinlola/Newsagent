import express from "express";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { NewsProps, defaultProps } from "../compositions/types";
import { assertEvenScale, renderOne, renderThumbnail } from "../render";
import { Analysis, analyzeUrl, normalizeAudio } from "../media";
import { putFile } from "./storage";

type Job = { status: "queued" | "running" | "succeeded" | "failed"; progress: number; output_keys: string[]; error: string | null };
type Output = { kind?: "video" | "thumbnail"; name?: string; scale?: number; format: "16x9" | "9x16"; width: number; height: number };

export function createApp(opts: { secret: string; maxConcurrent?: number; renderFn?: typeof renderOne; thumbFn?: typeof renderThumbnail; analyzeFn?: (url: string) => Promise<Analysis>; normalizeFn?: (file: string) => Promise<void> }) {
  const app = express();
  app.use(express.json({ limit: "1mb" }));
  const jobs = new Map<string, Job>();
  const queue: (() => Promise<void>)[] = [];
  let running = 0;
  const max = opts.maxConcurrent ?? Number(process.env.RENDER_JOBS_CONCURRENCY || 1);
  const render = opts.renderFn ?? renderOne;
  const renderThumb = opts.thumbFn ?? renderThumbnail;
  const analyze = opts.analyzeFn ?? analyzeUrl;
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

  app.post("/renders", (req, res) => {
    const { props, outputs, input_urls, output_prefix } = req.body as {
      composition: string; props: Partial<NewsProps>; outputs: Output[]; input_urls?: Record<string, string>; output_prefix: string;
    };
    if (!Array.isArray(outputs) || !outputs.length || !output_prefix || output_prefix.includes("..")) {
      return res.status(400).json({ error: "invalid request" });
    }
    const id = crypto.randomUUID();
    const job: Job = { status: "queued", progress: 0, output_keys: [], error: null };
    jobs.set(id, job);
    const merged: NewsProps = { ...defaultProps, ...props, anchorSrc: input_urls?.anchor ?? props.anchorSrc ?? null };
    queue.push(async () => {
      job.status = "running";
      const dir = fs.mkdtempSync(path.join(os.tmpdir(), "render-"));
      try {
        for (const [i, o] of outputs.entries()) {
          const thumb = o.kind === "thumbnail";
          const base = o.name ?? o.format;
          if (!/^[a-z0-9x_-]+$/i.test(base)) throw new Error("invalid output name");
          const file = path.join(dir, `${base}.${thumb ? "png" : "mp4"}`);
          if (thumb) await renderThumb(o.format, merged, file);
          else {
            assertEvenScale(o.width, o.height, o.scale ?? 1);
            await render({ format: o.format, props: merged, outFile: file, scale: o.scale, onProgress: (p) => { job.progress = (i + p) / outputs.length; } });
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
