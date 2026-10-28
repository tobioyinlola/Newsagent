import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { CF_PATHS, CF_VIEWBOX } from "./cf-paths";
import { CF, Fonts, SANS } from "./theme";

// Cover Founder News: the opening sting (about 5 s). Stripes sweep in, the logo builds piece by piece, the name rises out of a
// mask, a green wipe takes the picture away. Everything is drawn in code from the brand palette.
export const INTRO_SECONDS = 5;

const ease = Easing.bezier(0.22, 1, 0.36, 1);
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

const Beam: React.FC<{ x: number; w: number; delay: number; color: string; tilt?: number }> = ({ x, w, delay, color, tilt = -18 }) => {
  const f = useCurrentFrame();
  const { height } = useVideoConfig();
  const p = interpolate(f, [delay, delay + 28], [0, 1], { ...clamp, easing: ease });
  const out = interpolate(f, [118, 134], [0, 1], { ...clamp, easing: Easing.in(Easing.quad) });
  return (
    <div style={{ position: "absolute", left: x, top: -200, width: w, height: height + 400, background: color, transform: `skewX(${tilt}deg) translateY(${(1 - p) * -height - out * height}px)`, opacity: 0.9 }} />
  );
};

export const BrandIntro: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const u = Math.min(width, height) / 1080;
  const s = (delay: number, damping = 14) => spring({ frame: frame - delay, fps, config: { damping, stiffness: 120, mass: 0.8 } });

  const frameIn = interpolate(frame, [14, 40], [0, 1], { ...clamp, easing: ease });
  const barIn = s(30, 16);
  const cIn = s(38), fIn = s(46);
  const nameIn = interpolate(frame, [62, 84], [0, 1], { ...clamp, easing: ease });
  const tagIn = interpolate(frame, [84, 104], [0, 1], { ...clamp, easing: ease });
  const glow = interpolate(frame, [30, 70, 130], [0, 1, 0.6], clamp);
  const sweep = interpolate(frame, [56, 96], [-0.3, 1.3], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const wipe = interpolate(frame, [126, 148], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const logoScale = interpolate(frame, [0, 150], [0.94, 1.04], clamp);

  const piece = (i: number) => CF_PATHS[i];
  const popped = (v: number): React.CSSProperties => ({ transformBox: "fill-box", transformOrigin: "center", transform: `scale(${0.4 + 0.6 * v}) rotate(${(1 - v) * -14}deg)`, opacity: Math.min(1, v * 1.6) });

  const words = ["COVER", "FOUNDER", "NEWS"];
  return (
    <AbsoluteFill style={{ background: CF.ink, overflow: "hidden", fontFamily: SANS }}>
      <Fonts />
      {/* brand stripes, sweeping in from the top */}
      <Beam x={width * 0.58} w={width * 0.14} delay={0} color={CF.stripe} />
      <Beam x={width * 0.74} w={width * 0.08} delay={6} color="#3a3d31" />
      <Beam x={width * 0.84} w={width * 0.05} delay={12} color={CF.stripe} />
      <Beam x={width * 0.12} w={width * 0.03} delay={9} color={CF.stripe} />
      {/* soft glow behind the mark */}
      <div style={{ position: "absolute", left: "50%", top: "42%", width: 900 * u, height: 900 * u, transform: "translate(-50%,-50%)", background: `radial-gradient(circle, ${CF.green}33 0%, transparent 62%)`, opacity: glow }} />
      {/* accent bars: the brand's secondary colours, racing across the lower third like a news sting */}
      {[["#EB464B", 0], [CF.peach, 5], [CF.green, 10]].map(([c, d], i) => {
        const p = interpolate(frame, [Number(d) + 18, Number(d) + 44], [0, 1], { ...clamp, easing: ease });
        const o = interpolate(frame, [116, 132], [1, 0], clamp);
        return <div key={String(c)} style={{ position: "absolute", left: 0, bottom: (150 + i * 16) * u, height: 8 * u, width: `${p * 100}%`, background: String(c), opacity: o }} />;
      })}

      {/* the logo, built piece by piece */}
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", paddingBottom: 150 * u }}>
        <svg viewBox={CF_VIEWBOX} height={400 * u} style={{ display: "block", transform: `scale(${logoScale})`, filter: `drop-shadow(0 0 ${28 * u}px ${CF.green}55)` }} fill={CF.green} shapeRendering="geometricPrecision" aria-label="Cover Founder">
          <defs>
            <clipPath id="frameReveal"><rect x="1250" y="81" width="108.6" height={frameIn * 80} /></clipPath>
            <linearGradient id="shine" x1="0" x2="1"><stop offset="0" stopColor="#fff" stopOpacity="0" /><stop offset="0.5" stopColor="#fff" stopOpacity="0.85" /><stop offset="1" stopColor="#fff" stopOpacity="0" /></linearGradient>
            <clipPath id="logoShape">{CF_PATHS.slice(0, 4).map((p, i) => <path key={i} fillRule={p.rule} d={p.d} />)}</clipPath>
          </defs>
          <g clipPath="url(#frameReveal)"><path fillRule={piece(3).rule} d={piece(3).d} /></g>
          <g style={{ transform: `translateX(${(1 - barIn) * -90}px)`, opacity: Math.min(1, barIn * 1.5) }}><path fillRule={piece(0).rule} d={piece(0).d} /></g>
          <g style={popped(cIn)}><path fillRule={piece(1).rule} d={piece(1).d} /></g>
          <g style={popped(fIn)}><path fillRule={piece(2).rule} d={piece(2).d} /></g>
          <g style={{ opacity: interpolate(frame, [52, 66], [0, 1], clamp) }}><path fillRule={piece(4).rule} d={piece(4).d} fill={CF.green} /></g>
          {/* a band of light passing over the finished mark */}
          <g clipPath="url(#logoShape)"><rect x={1250 + sweep * 108} y="70" width="36" height="130" fill="url(#shine)" transform="skewX(-18)" opacity={sweep > -0.2 && sweep < 1.2 ? 1 : 0} /></g>
        </svg>
        {/* the name, each word rising out of its own mask */}
        <div style={{ position: "absolute", left: 0, right: 0, top: `calc(50% + ${150 * u}px)`, display: "flex", justifyContent: "center", gap: 28 * u }}>
          {words.map((w, i) => {
            const p = interpolate(nameIn, [i * 0.18, i * 0.18 + 0.64], [0, 1], { ...clamp, easing: ease });
            return (
              <div key={w} style={{ overflow: "hidden", height: 96 * u }}>
                <div style={{ transform: `translateY(${(1 - p) * 110}%)`, color: i === 2 ? CF.green : CF.white, fontWeight: 800, fontSize: 82 * u, letterSpacing: 6 * u, lineHeight: `${96 * u}px` }}>{w}</div>
              </div>
            );
          })}
        </div>
        <div style={{ position: "absolute", left: 0, right: 0, top: `calc(50% + ${262 * u}px)`, textAlign: "center", color: "#B9BCAE", fontSize: 30 * u, letterSpacing: 10 * u, textTransform: "uppercase", fontWeight: 500, opacity: tagIn, transform: `translateY(${(1 - tagIn) * 14}px)` }}>
          The AI newsroom for businesses
        </div>
      </AbsoluteFill>

      {/* the green wipe that takes us to the story */}
      <div style={{ position: "absolute", inset: 0, background: CF.green, transform: `translateX(${(1 - wipe) * 100}%) skewX(-12deg)`, transformOrigin: "left", width: "125%", marginLeft: "-10%" }} />
    </AbsoluteFill>
  );
};
