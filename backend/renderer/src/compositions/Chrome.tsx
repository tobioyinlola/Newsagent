import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

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
      <div style={{ position: "absolute", top: 40 * u, left: 48 * u, display: "flex", gap: 12 * u, alignItems: "center" }}>
        <div style={{ width: 14 * u, height: 44 * u, background: p.brand.accent }} />
        <div style={{ color: "#fff", fontWeight: 800, fontSize: 30 * u, letterSpacing: 2 * u, textTransform: "uppercase" }}>{p.channel.name}</div>
      </div>
      <div style={{ position: "absolute", top: 40 * u, right: 48 * u, textAlign: "right" }}>
        <div style={{ display: "inline-block", background: p.brand.accent, color: "#111", fontWeight: 900, fontSize: 28 * u, padding: `${6 * u}px ${18 * u}px`, textTransform: "uppercase", letterSpacing: 2 * u }}>{p.disclosures.tag}</div>
        <div style={{ color: "#fff", opacity: 0.9, fontSize: 22 * u, marginTop: 8 * u }}>{p.disclosures.anchor}</div>
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 72 * u, background: "#050B1A", overflow: "hidden", borderTop: `${4 * u}px solid ${p.brand.accent}` }}>
        <div style={{ whiteSpace: "nowrap", color: "#fff", fontSize: 32 * u, lineHeight: `${68 * u}px`, transform: `translateX(${tickerX}px)` }}>
          {ticker.repeat(Math.ceil((width * 2) / tickerW) + 2)}
        </div>
      </div>
    </>
  );
};

// The studio set behind the anchor.
export const Backdrop: React.FC<{ primary: string; accent: string }> = ({ primary, accent }) => {
  const { width, height } = useVideoConfig();
  const portrait = height > width;
  const u = Math.min(width, height) / 1080;
  return (
    <div style={{ position: "absolute", inset: 0, background: `linear-gradient(160deg, ${primary}, #050B1A 75%)` }}>
      <div style={{ position: "absolute", left: "-10%", top: "8%", width: "60%", height: "70%", background: "rgba(255,255,255,0.05)", transform: "skewX(-12deg)" }} />
      <div style={{ position: "absolute", right: "-5%", top: "15%", width: "35%", height: "55%", background: "rgba(255,255,255,0.04)", transform: "skewX(-12deg)" }} />
      <div style={{ position: "absolute", left: 0, right: 0, bottom: portrait ? "32%" : "20%", height: 6 * u, background: accent, opacity: 0.8 }} />
    </div>
  );
};
