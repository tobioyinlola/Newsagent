import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import path from "node:path";
import { NewsProps } from "./compositions/types";

let serveUrl: string | null = null;
export async function getBundle(): Promise<string> {
  if (!serveUrl) serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts"), publicDir: path.resolve(process.env.PUBLIC_DIR || "public") });
  return serveUrl;
}

const browserExecutable = process.env.CHROMIUM_PATH || undefined;

export async function renderOne(opts: {
  format: "16x9" | "9x16"; props: NewsProps; outFile: string; onProgress?: (p: number) => void;
}) {
  const url = await getBundle();
  const id = `NewsStudio-${opts.format}`;
  const comp = await selectComposition({ serveUrl: url, id, inputProps: opts.props, browserExecutable });
  await renderMedia({
    composition: comp, serveUrl: url, codec: "h264", audioCodec: "aac", outputLocation: opts.outFile,
    inputProps: opts.props, browserExecutable, // Do NOT force gl: "swangle". It was measured 2-3x slower than Chrome's default in docs/render-benchmarks.md.
    chromiumOptions: process.env.RENDER_GL ? { gl: process.env.RENDER_GL as "swangle" | "angle" | "egl" } : undefined,
    concurrency: process.env.RENDER_CONCURRENCY ? Number(process.env.RENDER_CONCURRENCY) : undefined,
    jpegQuality: process.env.RENDER_JPEG_QUALITY ? Number(process.env.RENDER_JPEG_QUALITY) : undefined,
    onProgress: ({ progress }) => opts.onProgress?.(progress),
  });
  return comp;
}

export async function renderThumbnail(format: "16x9" | "9x16", props: NewsProps, outFile: string) {
  const url = await getBundle();
  const comp = await selectComposition({ serveUrl: url, id: `NewsStudio-${format}`, inputProps: props, browserExecutable });
  await renderStill({ composition: comp, serveUrl: url, output: outFile, frame: 45, inputProps: props, browserExecutable });
}
