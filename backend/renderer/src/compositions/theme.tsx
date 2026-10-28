import React, { useEffect, useState } from "react";
import { AbsoluteFill, cancelRender, continueRender, delayRender, staticFile, useVideoConfig } from "remotion";
import { CF_PATHS, CF_SYMBOL_VIEWBOX } from "./cf-paths";

// Cover Founder brand (guideline v1.0). Channel graphics always use these; the startup's own brand kit only colours
// the lower-third marker, so every video reads as a Cover Founder video.
export const CF = {
  ink: "#222222",
  navy: "#191A30",
  stripe: "#2E3128", // the olive diagonal stripes on dark grounds
  green: "#C0FE73", // Pastel Green
  peach: "#FFBD59",
  white: "#FFFFFF",
} as const;

export const MONO = '"Inter", Helvetica, Arial, sans-serif'; // headlines: Inter Bold (one typeface everywhere)
export const SANS = '"Inter", Helvetica, Arial, sans-serif'; // body: Inter

const FONT_FILES: [string, string, number][] = [
  ["Inter", "fonts/Inter-Regular.woff2", 400],
  ["Inter", "fonts/Inter-Bold.woff2", 700],
];

// Fonts ship inside the render bundle (no network at render time). Rendering waits until they are loaded, so a frame
// can never be captured in a fallback font.
export const Fonts: React.FC = () => {
  const [handle] = useState(() => delayRender("Loading Cover Founder fonts"));
  useEffect(() => {
    Promise.all(
      FONT_FILES.map(async ([family, file, weight]) => {
        const face = new FontFace(family, `url(${staticFile(file)}) format("woff2")`, { weight: String(weight) });
        document.fonts.add(await face.load());
      }),
    )
      .then(() => continueRender(handle))
      .catch((e) => cancelRender(e));
  }, [handle]);
  return null;
};

// The CF symbol (no name bar) for the channel bug; the full logo is too small to read at bug size (guideline p.13).
export const CFSymbol: React.FC<{ height: number; color?: string }> = ({ height, color = CF.green }) => (
  <svg viewBox={CF_SYMBOL_VIEWBOX} height={height} style={{ display: "block" }} fill={color} aria-label="Cover Founder">
    {CF_PATHS.slice(1, 4).map((p, i) => <path key={i} fillRule={p.rule} d={p.d} />)}
  </svg>
);

// The guideline's dark ground with its signature olive diagonal stripes.
export const StripesBackground: React.FC = () => {
  const { width, height } = useVideoConfig();
  const portrait = height > width;
  return (
    <AbsoluteFill style={{ background: CF.ink }}>
      <svg viewBox="0 0 400 400" preserveAspectRatio="none" width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        <g fill={CF.stripe}>
          <polygon points={portrait ? "150,0 330,0 255,170 75,170" : "215,0 355,0 285,200 145,200"} />
          <polygon points={portrait ? "250,230 330,230 255,400 175,400" : "275,200 345,200 275,400 205,400"} />
          <polygon points={portrait ? "330,230 400,230 325,400 255,400" : "345,200 395,200 325,400 275,400"} />
        </g>
      </svg>
    </AbsoluteFill>
  );
};
