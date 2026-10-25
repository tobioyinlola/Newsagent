import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { CF, CFSymbol, MONO } from "./theme";

// A presenter clip is cut off at the top of its frame; fade that edge into the set instead of showing a hard line.
export const SOFT_TOP: React.CSSProperties = {
  WebkitMaskImage: "linear-gradient(to bottom, transparent 0, #000 7%)",
  maskImage: "linear-gradient(to bottom, transparent 0, #000 7%)",
};

// An original TV news set drawn in code (no real network's look): glass-panel wall with lit screens, a soft spotlight
// behind the presenter, and a curved desk in front of her. Colours come from the Cover Founder brand.
const W = 1920;
const H = 1080;

export const NewsBackdrop: React.FC = () => {
  const frame = useCurrentFrame();
  const sweep = interpolate(frame % 600, [0, 600], [-0.25, 1.25]); // a slow band of light crossing the wall
  const panels = Array.from({ length: 12 }, (_, i) => i);
  return (
    <AbsoluteFill style={{ background: "#0a0e1c" }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" width="100%" height="100%" style={{ position: "absolute", inset: 0 }}>
        <defs>
          <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#0d1428" />
            <stop offset="0.6" stopColor="#141d3a" />
            <stop offset="1" stopColor="#090c18" />
          </linearGradient>
          <radialGradient id="spot" cx="0.5" cy="0.42" r="0.5">
            <stop offset="0" stopColor="#c0fe73" stopOpacity="0.20" />
            <stop offset="0.45" stopColor="#4e6bd8" stopOpacity="0.14" />
            <stop offset="1" stopColor="#000" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="screen" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#1d2c5a" />
            <stop offset="1" stopColor="#0c1330" />
          </linearGradient>
          <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#0b1022" />
            <stop offset="1" stopColor="#05070f" />
          </linearGradient>
          <linearGradient id="beam" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#fff" stopOpacity="0" />
            <stop offset="0.5" stopColor="#c8d6ff" stopOpacity="0.10" />
            <stop offset="1" stopColor="#fff" stopOpacity="0" />
          </linearGradient>
        </defs>
        <rect width={W} height={H} fill="url(#wall)" />
        {/* vertical glass panels with lit seams */}
        {panels.map((i) => (
          <g key={i}>
            <rect x={i * 160 + 4} y={0} width={152} height={820} fill="#ffffff" opacity={i % 2 ? 0.018 : 0.04} />
            <rect x={i * 160} y={0} width={3} height={820} fill="#7f98ff" opacity={0.18} />
          </g>
        ))}
        {/* two big screens: world grid (left) and the channel mark (right) */}
        <g>
          <rect x={150} y={150} width={470} height={290} rx={8} fill="url(#screen)" stroke="#3e5bb8" strokeWidth={3} />
          {Array.from({ length: 7 }, (_, i) => (
            <ellipse key={i} cx={385} cy={295} rx={30 + i * 32} ry={105} fill="none" stroke="#6f8cff" strokeOpacity={0.35} strokeWidth={1.5} />
          ))}
          {Array.from({ length: 6 }, (_, i) => (
            <line key={i} x1={160} x2={610} y1={190 + i * 45} y2={190 + i * 45} stroke="#6f8cff" strokeOpacity={0.22} strokeWidth={1.5} />
          ))}
          <circle cx={385} cy={295} r={7} fill={CF.green} />
        </g>
        <g>
          <rect x={1300} y={150} width={470} height={290} rx={8} fill="url(#screen)" stroke="#3e5bb8" strokeWidth={3} />
          <rect x={1330} y={400} width={410} height={6} fill={CF.green} opacity={0.9} />
          {[0, 1, 2].map((i) => (
            <rect key={i} x={1330} y={330 + i * 0} width={0} height={0} />
          ))}
        </g>
        {/* the presenter's spotlight and a slow band of light */}
        <rect width={W} height={H} fill="url(#spot)" />
        <rect x={sweep * W - 160} y={0} width={320} height={820} fill="url(#beam)" />
        {/* glossy floor */}
        <rect x={0} y={820} width={W} height={260} fill="url(#floor)" />
        <rect x={0} y={820} width={W} height={3} fill="#7f98ff" opacity={0.35} />
      </svg>
      {/* the right screen's content as real text, so it stays sharp */}
      <ScreenText />
    </AbsoluteFill>
  );
};

const ScreenText: React.FC = () => {
  const { width, height } = useVideoConfig();
  const u = Math.min(width / W, height / H) * (height > width ? 0.56 : 1);
  const sx = width / W;
  const sy = height / H;
  const s = Math.max(sx, sy); // matches preserveAspectRatio="slice"
  const ox = (width - W * s) / 2;
  const oy = (height - H * s) / 2;
  const at = (x: number, y: number) => ({ left: ox + x * s, top: oy + y * s });
  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      <div style={{ position: "absolute", ...at(1335, 200), color: CF.green, fontFamily: MONO, fontWeight: 700, fontSize: 30 * s, letterSpacing: 4 * s, textTransform: "uppercase" }}>Startup desk</div>
      <div style={{ position: "absolute", ...at(1335, 252), color: CF.white, fontFamily: MONO, fontWeight: 700, fontSize: 54 * s, lineHeight: 1.1 }}>Featured<br />tonight</div>
      <div style={{ position: "absolute", ...at(1655, 190), opacity: 0.9 }}><CFSymbol height={70 * s * (u / u)} /></div>
    </div>
  );
};

// The desk in front of the presenter; drawn above her so it hides her lower edge and her hands.
export const NewsDesk: React.FC = () => {
  const { width, height } = useVideoConfig();
  const portrait = height > width;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio={portrait ? "xMidYMax slice" : "xMidYMax slice"} width="100%" height="100%">
        <defs>
          <linearGradient id="deskTop" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#3a4a86" />
            <stop offset="0.35" stopColor="#1c2547" />
            <stop offset="1" stopColor="#0f1530" />
          </linearGradient>
          <linearGradient id="deskFront" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#0a0f22" />
            <stop offset="0.5" stopColor="#18224a" />
            <stop offset="1" stopColor="#0a0f22" />
          </linearGradient>
        </defs>
        {/* desk top: a shallow arc */}
        <path d="M-40 862 Q960 780 1960 862 L1960 905 Q960 835 -40 905 Z" fill="url(#deskTop)" />
        <path d="M-40 862 Q960 780 1960 862" fill="none" stroke="#dbe6ff" strokeOpacity={0.55} strokeWidth={3} />
        {/* desk front with a lit green edge and the channel mark */}
        <path d="M-40 905 Q960 835 1960 905 L1960 1010 L-40 1010 Z" fill="url(#deskFront)" />
        <path d="M-40 905 Q960 835 1960 905" fill="none" stroke="#c0fe73" strokeWidth={5} strokeOpacity={0.9} />
        {[480, 720, 1200, 1440].map((x) => (
          <line key={x} x1={x} x2={x} y1={880} y2={1008} stroke="#6f8cff" strokeOpacity={0.18} strokeWidth={2} />
        ))}
      </svg>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: "11%", display: "flex", justifyContent: "center", opacity: 0.95 }}>
        <CFSymbol height={Math.min(width, height) * 0.075} />
      </div>
    </AbsoluteFill>
  );
};
