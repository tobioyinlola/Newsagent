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

export type Palette = {
  wallTop: string; wallMid: string; wallBottom: string; seam: string; panel: string; panelOpacity: number;
  spot1: string; spot2: string; screenA: string; screenB: string; screenLine: string; floorA: string; floorB: string;
  deskTop1: string; deskTop2: string; deskTop3: string; deskFront1: string; deskFront2: string; rim: string; edge: string;
  screenText: string; screenSub: string; beam: string;
};

// Studio looks the owner can choose between (project.studio_id). Unknown ids fall back to "navy".
export const PALETTES: Record<string, Palette> = {
  navy: {
    wallTop: "#0d1428", wallMid: "#141d3a", wallBottom: "#090c18", seam: "#7f98ff", panel: "#ffffff", panelOpacity: 0.03,
    spot1: "#c0fe73", spot2: "#4e6bd8", screenA: "#1d2c5a", screenB: "#0c1330", screenLine: "#6f8cff", floorA: "#0b1022", floorB: "#05070f",
    deskTop1: "#3a4a86", deskTop2: "#1c2547", deskTop3: "#0f1530", deskFront1: "#0a0f22", deskFront2: "#18224a", rim: "#dbe6ff", edge: "#c0fe73",
    screenText: "#ffffff", screenSub: "#c0fe73", beam: "#c8d6ff",
  },
  daylight: {
    wallTop: "#dfe7f5", wallMid: "#c3cfe6", wallBottom: "#9eacc9", seam: "#ffffff", panel: "#ffffff", panelOpacity: 0.28,
    spot1: "#ffffff", spot2: "#9ec1ff", screenA: "#ffffff", screenB: "#dbe6fb", screenLine: "#5e82d6", floorA: "#8c9bbb", floorB: "#6b7a9c",
    deskTop1: "#ffffff", deskTop2: "#e4eaf6", deskTop3: "#c2cde6", deskFront1: "#aab6d2", deskFront2: "#e6ecf8", rim: "#ffffff", edge: "#5fae14",
    screenText: "#1b2a55", screenSub: "#3d7f0c", beam: "#ffffff",
  },
  emerald: {
    wallTop: "#0c1a14", wallMid: "#12281f", wallBottom: "#07100c", seam: "#c0fe73", panel: "#c0fe73", panelOpacity: 0.035,
    spot1: "#c0fe73", spot2: "#1f8a5b", screenA: "#143a2b", screenB: "#0a1d16", screenLine: "#7fe0a8", floorA: "#09150f", floorB: "#040a07",
    deskTop1: "#2f6a4f", deskTop2: "#143a2b", deskTop3: "#0b1f17", deskFront1: "#07140e", deskFront2: "#123325", rim: "#d9ffe9", edge: "#c0fe73",
    screenText: "#ffffff", screenSub: "#c0fe73", beam: "#c0fe73",
  },
  sunrise: {
    wallTop: "#20314f", wallMid: "#3a4f7a", wallBottom: "#17213a", seam: "#ffd9a0", panel: "#ffe3b8", panelOpacity: 0.05,
    spot1: "#ffbd59", spot2: "#ff8a5b", screenA: "#2b4170", screenB: "#16223f", screenLine: "#ffc980", floorA: "#1a2440", floorB: "#0d1327",
    deskTop1: "#6a7fb3", deskTop2: "#33456f", deskTop3: "#1e2b4b", deskFront1: "#141c33", deskFront2: "#2b3c66", rim: "#ffeccf", edge: "#ffbd59",
    screenText: "#ffffff", screenSub: "#ffbd59", beam: "#ffd9a0",
  },
};
export const STUDIO_LABELS: Record<string, string> = { navy: "Evening navy", daylight: "Daylight", emerald: "Brand green", sunrise: "Sunrise" };

const StudioContext = React.createContext<Palette>(PALETTES.navy);
export const StudioProvider: React.FC<{ studio?: string; children: React.ReactNode }> = ({ studio, children }) => (
  <StudioContext.Provider value={PALETTES[studio ?? ""] ?? PALETTES.navy}>{children}</StudioContext.Provider>
);

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
