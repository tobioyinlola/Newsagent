import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { NewsBackdrop } from "./NewsSet";
import { CF, CFSymbol, MONO, SANS } from "./theme";

type ChromeProps = {
  channel: { name: string };
  disclosures: { tag: string; anchor: string };
  brand: { accent: string };
  tickerLines: string[];
};

// Elements shown on EVERY video, in every composition: channel bug, mandatory disclosures, ticker.
// Keeping them in one place guarantees the interview cut can never drop a disclosure (hard rule 2).
export const Chrome: React.FC<ChromeProps> = (p) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const u = Math.min(width, height) / 1080;
  const ticker = p.tickerLines.join("   •   ") + "   •   ";
  const tickerW = ticker.length * 22 * u;
  const tickerX = -((frame * 3 * u) % tickerW);
  return (
    <>
      {/* channel bug: CF symbol + name */}
      <div style={{ position: "absolute", top: 40 * u, left: 48 * u, display: "flex", gap: 16 * u, alignItems: "center" }}>
        <CFSymbol height={52 * u} />
        <div style={{ color: CF.white, fontFamily: MONO, fontWeight: 700, fontSize: 30 * u, letterSpacing: 1 * u, textTransform: "uppercase" }}>{p.channel.name}</div>
      </div>
      {/* mandatory disclosures (hard rule 2): tag + anchor label, always on screen */}
      <div style={{ position: "absolute", top: 40 * u, right: 48 * u, textAlign: "right" }}>
        <div style={{ display: "inline-block", background: CF.peach, color: CF.ink, fontFamily: MONO, fontWeight: 700, fontSize: 28 * u, padding: `${6 * u}px ${18 * u}px`, textTransform: "uppercase", letterSpacing: 2 * u }}>{p.disclosures.tag}</div>
        <div style={{ color: CF.white, fontFamily: SANS, fontSize: 22 * u, marginTop: 8 * u }}>{p.disclosures.anchor}</div>
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
