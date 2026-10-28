import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { CFLogo, CF, Fonts, SANS } from "./theme";

// Cover Founder News: the closing card (about 6 s): the invitation, the address, the places we reach. It holds on screen to the last frame (no fade out).
export const OUTRO_SECONDS = 6;

const ease = Easing.bezier(0.22, 1, 0.36, 1);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const REGIONS = ["United States", "Canada", "Europe", "East Africa", "Nigeria"];

export const BrandOutro: React.FC = () => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const u = Math.min(width, height) / 1080;
  const rise = (a: number, b: number) => interpolate(frame, [a, b], [0, 1], { ...clamp, easing: ease });

  const lineA = rise(6, 30), lineB = rise(16, 40);
  const url = rise(34, 62);
  const underline = rise(60, 86);
  const chips = (i: number) => rise(86 + i * 6, 108 + i * 6);
  const logoIn = rise(100, 124);
  const pulse = 1 + 0.015 * Math.sin(frame / 8) * (frame > 90 ? 1 : 0);

  const tick = "ON COVER FOUNDER  •  PRESS DISTRIBUTION  •  25K+ MEDIA PLATFORMS  •  UNITED STATES  •  CANADA  •  EUROPE  •  EAST AFRICA  •  NIGERIA  •  ";
  const tickerX = -((frame * 4 * u) % (tick.length * 20 * u));

  return (
    <AbsoluteFill style={{ background: CF.ink, overflow: "hidden", fontFamily: SANS }}>
      <Fonts />
      {/* stripes + moving light */}
      {[[0.62, 0.15], [0.8, 0.07], [0.9, 0.04]].map(([x, w], i) => (
        <div key={i} style={{ position: "absolute", left: width * x, top: -200, width: width * w, height: height + 400, background: i === 1 ? "#3a3d31" : CF.stripe, transform: `skewX(-18deg) translateY(${(1 - rise(i * 5, 26 + i * 5)) * -height}px)` }} />
      ))}
      <div style={{ position: "absolute", left: "38%", top: "46%", width: 1100 * u, height: 1100 * u, transform: "translate(-50%,-50%)", background: `radial-gradient(circle, ${CF.green}26 0%, transparent 60%)` }} />

      <AbsoluteFill style={{ justifyContent: "center", paddingLeft: 140 * u, paddingRight: 140 * u }}>
        {/* the invitation */}
        <div style={{ overflow: "hidden", height: 64 * u }}>
          <div style={{ color: CF.white, fontWeight: 600, fontSize: 46 * u, lineHeight: `${64 * u}px`, transform: `translateY(${(1 - lineA) * 110}%)` }}>Get your own news coverage</div>
        </div>
        <div style={{ overflow: "hidden", height: 64 * u }}>
          <div style={{ color: CF.white, fontWeight: 600, fontSize: 46 * u, lineHeight: `${64 * u}px`, transform: `translateY(${(1 - lineB) * 110}%)` }}>and press distribution on</div>
        </div>
        {/* the address */}
        <div style={{ marginTop: 26 * u, overflow: "hidden", height: 190 * u }}>
          <div style={{ color: CF.green, fontWeight: 800, fontSize: 168 * u, letterSpacing: -4 * u, lineHeight: `${190 * u}px`, transform: `translateY(${(1 - url) * 105}%) scale(${pulse})`, transformOrigin: "left center", whiteSpace: "nowrap" }}>coverfounder.com</div>
        </div>
        <div style={{ height: 10 * u, width: `${underline * 100}%`, maxWidth: 1180 * u, background: `linear-gradient(90deg, ${CF.green}, ${CF.peach})`, marginTop: 4 * u }} />
        {/* where it reaches */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 14 * u, marginTop: 44 * u }}>
          {REGIONS.map((r, i) => (
            <span key={r} style={{ opacity: chips(i), transform: `translateY(${(1 - chips(i)) * 24}px)`, border: `${3 * u}px solid ${CF.green}`, color: CF.white, padding: `${10 * u}px ${22 * u}px`, fontSize: 28 * u, fontWeight: 600, borderRadius: 4 * u, background: "rgba(192,254,115,0.08)" }}>{r}</span>
          ))}
        </div>
      </AbsoluteFill>

      {/* the logo, bottom-right, and the ticker underneath */}
      <div style={{ position: "absolute", right: 90 * u, bottom: 120 * u, opacity: logoIn, transform: `translateY(${(1 - logoIn) * 30}px) scale(${0.9 + 0.1 * logoIn})` }}>
        <CFLogo height={190 * u} />
      </div>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: 72 * u, background: CF.ink, borderTop: `${4 * u}px solid ${CF.green}`, overflow: "hidden" }}>
        <div style={{ whiteSpace: "nowrap", color: CF.white, fontSize: 32 * u, lineHeight: `${68 * u}px`, fontWeight: 500, transform: `translateX(${tickerX}px)` }}>{tick.repeat(6)}</div>
      </div>
    </AbsoluteFill>
  );
};
