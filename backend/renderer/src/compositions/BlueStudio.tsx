import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { CF, CFSymbol, MONO, SANS } from "./theme";

// A bright blue TV news studio drawn in code: a curved wall with a lit ceiling band, three big screens (the two side
// screens angled towards the presenter), and a glass desk. Original artwork; the words on the screens are ours.
const W = 1920;
const H = 1080;

// Place content in 1920x1080 "design space" so it scales and crops exactly like the SVG layers (slice).
const useDesign = () => {
  const { width, height } = useVideoConfig();
  const s = Math.max(width / W, height / H);
  return { s, ox: (width - W * s) / 2, oy: (height - H * s) / 2 };
};

const Screen: React.FC<{ x: number; y: number; w: number; h: number; side: "left" | "right" }> = ({ x, y, w, h, side }) => {
  const { s, ox, oy } = useDesign();
  const frame = useCurrentFrame();
  const pulse = interpolate(Math.sin(frame / 22), [-1, 1], [0.92, 1]);
  return (
    <div
      style={{
        position: "absolute", left: ox + x * s, top: oy + y * s, width: w * s, height: h * s,
        transform: `perspective(${1500 * s}px) rotateY(${side === "left" ? 24 : -24}deg)`, transformOrigin: side === "left" ? "left center" : "right center",
        background: "linear-gradient(180deg,#eaf1ff 0%,#9db8ec 55%,#3a5fb0 100%)", border: `${5 * s}px solid #dfe9fb`, boxShadow: `0 0 ${50 * s}px rgba(120,170,255,0.55)`, overflow: "hidden",
      }}
    >
      {/* blurred city bars: a lit glass screen, with no words on it */}
      <div style={{ position: "absolute", inset: 0, background: "repeating-linear-gradient(90deg, rgba(20,50,120,.25) 0 14%, rgba(255,255,255,.12) 14% 20%)", filter: `blur(${3 * s}px)` }} />
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, height: "14%", background: "rgba(10,30,80,.55)" }} />
    </div>
  );
};

export const BlueBackdrop: React.FC = () => {
  const frame = useCurrentFrame();
  const sweep = interpolate(frame % 720, [0, 720], [-0.2, 1.2]);
  return (
    <AbsoluteFill style={{ background: "#0f3f86" }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" width="100%" height="100%" style={{ position: "absolute", inset: 0 }}>
        <defs>
          <linearGradient id="bwall" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#2f7fdc" />
            <stop offset="0.55" stopColor="#1b62bb" />
            <stop offset="1" stopColor="#0e3b80" />
          </linearGradient>
          <linearGradient id="bceil" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#ffffff" />
            <stop offset="1" stopColor="#bcd4f6" />
          </linearGradient>
          <radialGradient id="bspot" cx="0.5" cy="0.45" r="0.55">
            <stop offset="0" stopColor="#ffffff" stopOpacity="0.38" />
            <stop offset="0.5" stopColor="#9cc4ff" stopOpacity="0.16" />
            <stop offset="1" stopColor="#000" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="bfloor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#9db4d6" />
            <stop offset="1" stopColor="#4d6690" />
          </linearGradient>
          <linearGradient id="bbeam" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#fff" stopOpacity="0" />
            <stop offset="0.5" stopColor="#fff" stopOpacity="0.12" />
            <stop offset="1" stopColor="#fff" stopOpacity="0" />
          </linearGradient>
        </defs>
        <rect width={W} height={H} fill="url(#bwall)" />
        {/* curved ceiling band and a thinner light arc */}
        <path d={`M0 0 H${W} V78 Q${W / 2} 168 0 78 Z`} fill="url(#bceil)" />
        <path d={`M0 98 Q${W / 2} 190 ${W} 98`} fill="none" stroke="#e8f1ff" strokeOpacity={0.7} strokeWidth={6} />
        {/* dark side pillars and soft vertical wall lights */}
        <rect x={0} y={0} width={46} height={830} fill="#1a2a47" opacity={0.85} />
        <rect x={W - 46} y={0} width={46} height={830} fill="#1a2a47" opacity={0.85} />
        {[300, 620, 1300, 1620].map((x) => (
          <rect key={x} x={x} y={120} width={6} height={700} fill="#cfe2ff" opacity={0.22} />
        ))}
        {/* centre screen: a globe */}
        <g>
          <rect x={650} y={150} width={620} height={330} rx={6} fill="#1a4fa6" stroke="#dfe9fb" strokeWidth={5} />
          <circle cx={960} cy={338} r={128} fill="#2b78d6" stroke="#bcd4f6" strokeWidth={3} />
          {[34, 72, 106].map((rx) => (
            <ellipse key={rx} cx={960} cy={338} rx={rx} ry={128} fill="none" stroke="#bcd4f6" strokeOpacity={0.55} strokeWidth={1.5} />
          ))}
          {[-70, 0, 70].map((dy) => (
            <ellipse key={dy} cx={960} cy={338 + dy} rx={Math.sqrt(128 * 128 - dy * dy)} ry={12} fill="none" stroke="#bcd4f6" strokeOpacity={0.5} strokeWidth={1.5} />
          ))}
          <path transform="translate(0 23) translate(960 315) scale(0.85) translate(-960 -315)" d="M880 250 q30 -30 70 -10 q25 20 5 45 q-20 25 -55 12 q-30 -18 -20 -47z M985 300 q40 -20 60 10 q10 35 -20 55 q-30 10 -45 -20 q-8 -24 5 -45z M900 345 q25 -8 40 12 q5 18 -15 28 q-25 0 -25 -40z" fill="#8cc0ff" opacity={0.75} />
        </g>
        <rect width={W} height={H} fill="url(#bspot)" />
        <rect x={sweep * W - 200} y={110} width={400} height={700} fill="url(#bbeam)" />
        {/* glossy studio floor behind the desk */}
        <rect x={0} y={830} width={W} height={250} fill="url(#bfloor)" />
        <rect x={0} y={830} width={W} height={4} fill="#eaf2ff" opacity={0.8} />
      </svg>
      <Screen x={110} y={120} w={470} h={330} side="left" />
      <Screen x={1340} y={120} w={470} h={330} side="right" />
      <BrandMark />
    </AbsoluteFill>
  );
};

const BrandMark: React.FC = () => {
  const { s, ox, oy } = useDesign();
  return (
    <div style={{ position: "absolute", left: ox + 790 * s, top: oy + 162 * s, width: 340 * s, display: "flex", justifyContent: "center", gap: 12 * s, alignItems: "center", opacity: 0.95 }}>
      <CFSymbol height={38 * s} color="#ffffff" />
      <span style={{ color: "#fff", fontFamily: MONO, fontWeight: 700, fontSize: 24 * s, letterSpacing: 2 * s, textTransform: "uppercase" }}>Cover Founder</span>
    </div>
  );
};

// The glass desk in front of the presenter, drawn above her.
export const BlueDesk: React.FC = () => {
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMax slice" width="100%" height="100%">
        <defs>
          <linearGradient id="gtop" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f4f8ff" stopOpacity="0.96" />
            <stop offset="0.25" stopColor="#c7dafa" stopOpacity="0.93" />
            <stop offset="1" stopColor="#6f93cf" stopOpacity="0.95" />
          </linearGradient>
          <linearGradient id="gfront" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#8fb0e6" stopOpacity="0.95" />
            <stop offset="1" stopColor="#35568f" stopOpacity="0.98" />
          </linearGradient>
        </defs>
        {/* desk top: a wide shallow arc */}
        <path d="M-40 872 Q960 800 1960 872 L1960 930 Q960 868 -40 930 Z" fill="url(#gtop)" />
        <path d="M-40 872 Q960 800 1960 872" fill="none" stroke="#ffffff" strokeWidth={4} />
        {/* reflections of the screens in the glass */}
        <g opacity={0.28}>
          <polygon points="170,898 540,892 540,918 170,924" fill="#ffd28a" />
          <polygon points="1380,892 1750,898 1750,924 1380,918" fill="#ffd28a" />
        </g>
        {/* front glass panel with a bright edge and metal clamps */}
        <path d="M-40 930 Q960 868 1960 930 L1960 1010 L-40 1010 Z" fill="url(#gfront)" />
        <path d="M-40 930 Q960 868 1960 930" fill="none" stroke="#e8f1ff" strokeWidth={5} />
        {[70, 1850].map((x) => (
          <g key={x}>
            <rect x={x - 18} y={925} width={36} height={36} rx={6} fill="#aab6c8" stroke="#6b7a92" strokeWidth={3} />
            <circle cx={x} cy={943} r={9} fill="#dfe6f2" />
          </g>
        ))}
      </svg>
      <div style={{ position: "absolute", left: 0, right: 0, bottom: "10%", display: "flex", justifyContent: "center", opacity: 0.9 }}>
        <CFSymbol height={Math.min(width, height) * 0.07} color="#ffffff" />
      </div>
    </AbsoluteFill>
  );
};
