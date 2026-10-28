import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { NewsBackdrop } from "./NewsSet";
import { CF, CFLogo, SANS } from "./theme";

type ChromeProps = {
  channel: { name: string };
  disclosures: { tag: string; anchor: string };
  brand: { accent: string };
  tickerLines: string[];
};

// A dark plate keeps the channel bug and the mandatory labels readable on any studio, including a bright one.
const PLATE = "rgba(14, 22, 44, 0.78)";

// Elements shown on EVERY video, in every composition: the channel logo and the ticker. (The AI-presenter disclosure travels
// with the video's captions, description and share page rather than as an on-screen label.)
export const Chrome: React.FC<ChromeProps> = (p) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const u = Math.min(width, height) / 1080;
  const ticker = p.tickerLines.join("   •   ") + "   •   ";
  const tickerW = ticker.length * 22 * u;
  const tickerX = -((frame * 3 * u) % tickerW);
  return (
    <>
      {/* channel mark: the primary Cover Founder logo, top-left, on every video */}
      <div style={{ position: "absolute", top: 24 * u, left: 28 * u, background: CF.navy, padding: 8 * u, borderRadius: 4 * u }}>
        <CFLogo height={150 * u} />
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 72 * u, background: CF.ink, overflow: "hidden", borderTop: `${4 * u}px solid ${CF.green}` }}>
        <div style={{ whiteSpace: "nowrap", color: CF.white, fontFamily: SANS, fontSize: 32 * u, lineHeight: `${68 * u}px`, transform: `translateX(${tickerX}px)` }}>
          {ticker.repeat(Math.ceil((width * 2) / tickerW) + 2)}
        </div>
      </div>
    </>
  );
};

// The studio set behind the anchor: an original TV news set (see NewsSet.tsx).
export const Backdrop: React.FC<{ primary?: string; accent?: string }> = () => <NewsBackdrop />;
