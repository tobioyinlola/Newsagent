import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { CF } from "./theme";

// The stand-in presenter shown when no avatar video is available (mock mode, or a vendor outage): an illustrated news
// anchor in a suit with a lapel mic. It breathes, sways, blinks and moves its mouth while the video plays, so a draft
// reads like a bulletin. It is a placeholder, not a likeness of anyone; the vendor's real presenter replaces it.
const SKIN = "#9a6545";
const SKIN_SHADE = "#7f4f34";
const HAIR = "#15110f";

export const AnchorFigure: React.FC<{ height: string }> = ({ height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const breathe = Math.sin(t * 1.6) * 1.2; // shoulders rise and fall
  const sway = Math.sin(t * 0.7) * 1.6; // slow head turn
  const nod = Math.sin(t * 2.3) * 0.8 + Math.sin(t * 5.1) * 0.4; // emphasis on words
  // blink every ~3.5 s for ~0.15 s
  const phase = (t + 0.9) % 3.5;
  const blink = phase < 0.15 ? 1 - Math.abs(phase - 0.075) / 0.075 : 0;
  // speech: syllable-rate open/close with phrase pauses
  const talking = Math.sin(t * 1.9) > -0.55 ? 1 : 0.15;
  const mouth = talking * Math.abs(Math.sin(t * 11.5) * 0.65 + Math.sin(t * 7.3) * 0.35);
  const mouthH = 1.5 + mouth * 9;
  const eyeH = 4.2 * (1 - blink * 0.92);

  return (
    <svg viewBox="0 0 300 380" style={{ height }} role="img" aria-label="Stand-in news anchor">
      <defs>
        <linearGradient id="suit" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#0f1730" />
          <stop offset="0.5" stopColor="#1d2b52" />
          <stop offset="1" stopColor="#0f1730" />
        </linearGradient>
        <linearGradient id="skin" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ad7650" />
          <stop offset="1" stopColor={SKIN_SHADE} />
        </linearGradient>
        <radialGradient id="rim" cx="0.5" cy="0.4" r="0.7">
          <stop offset="0.7" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="1" stopColor={CF.green} stopOpacity="0.16" />
        </radialGradient>
      </defs>

      <ellipse cx="150" cy="372" rx="130" ry="10" fill="#000" opacity="0.25" />

      <g transform={`translate(0 ${breathe})`}>
        {/* jacket and shoulders */}
        <path d="M18 380 C18 300 52 262 112 250 L188 250 C248 262 282 300 282 380Z" fill="url(#suit)" />
        {/* shirt and tie */}
        <path d="M112 250 L150 322 L188 250 L172 244 L150 262 L128 244Z" fill="#f4f4f1" />
        <path d="M143 262 L157 262 L162 276 L150 350 L138 276Z" fill={CF.green} />
        <path d="M143 262 L157 262 L159 270 L141 270Z" fill="#8fc54a" />
        {/* lapels */}
        <path d="M112 250 L150 330 L132 380 L84 380 L96 290Z" fill="#162244" />
        <path d="M188 250 L150 330 L168 380 L216 380 L204 290Z" fill="#162244" />
        <path d="M112 250 L128 244 L150 322Z" fill="#101a35" />
        <path d="M188 250 L172 244 L150 322Z" fill="#101a35" />
        {/* lapel microphone */}
        <g>
          <path d="M196 292 C204 300 208 316 204 336" stroke="#0b0b0b" strokeWidth="1.6" fill="none" />
          <rect x="190" y="282" width="12" height="17" rx="5" fill="#2a2a2a" />
          <rect x="192.5" y="285" width="7" height="3" rx="1.5" fill="#555" />
        </g>
      </g>

      <g transform={`translate(${sway} ${breathe * 0.6 + nod}) rotate(${sway * 0.35} 150 215)`}>
        {/* neck */}
        <path d="M126 196 L126 252 C136 266 164 266 174 252 L174 196Z" fill={SKIN_SHADE} />
        <path d="M126 236 C140 252 160 252 174 236 L174 252 C164 266 136 266 126 252Z" fill="#6c4129" opacity="0.55" />
        {/* ears */}
        <ellipse cx="95" cy="150" rx="9" ry="15" fill={SKIN_SHADE} />
        <ellipse cx="205" cy="150" rx="9" ry="15" fill={SKIN_SHADE} />
        {/* head */}
        <path d="M100 118 C100 70 126 54 150 54 C174 54 200 70 200 118 L200 158 C200 196 178 218 150 218 C122 218 100 196 100 158Z" fill="url(#skin)" />
        {/* hair */}
        <path d="M96 128 C90 70 120 40 152 40 C186 40 212 66 204 128 C200 104 186 84 150 82 C118 82 102 100 96 128Z" fill={HAIR} />
        <path d="M120 60 C140 46 176 48 194 68" stroke="#3a312c" strokeWidth="2.2" fill="none" opacity="0.7" />
        {/* brows */}
        <path d="M113 117 C122 111 134 111 142 116" stroke={HAIR} strokeWidth="4.5" strokeLinecap="round" fill="none" />
        <path d="M158 116 C166 111 178 111 187 117" stroke={HAIR} strokeWidth="4.5" strokeLinecap="round" fill="none" />
        {/* eyes */}
        <g>
          <ellipse cx="127" cy="132" rx="9.5" ry={eyeH + 0.4} fill="#f6f1ea" />
          <ellipse cx="173" cy="132" rx="9.5" ry={eyeH + 0.4} fill="#f6f1ea" />
          <ellipse cx={127 + sway * 0.3} cy="132.5" rx="4.4" ry={Math.min(eyeH, 4.2)} fill="#2a1a10" />
          <ellipse cx={173 + sway * 0.3} cy="132.5" rx="4.4" ry={Math.min(eyeH, 4.2)} fill="#2a1a10" />
        </g>
        {/* nose */}
        <path d="M150 134 C146 152 142 160 146 166 C150 169 154 169 158 166 C162 160 154 152 150 134Z" fill={SKIN_SHADE} opacity="0.45" />
        {/* mouth: moves with the speech */}
        <g transform="translate(150 185)">
          <path d={`M-17 0 C-9 ${-2} 9 ${-2} 17 0 C9 ${mouthH + 2} -9 ${mouthH + 2} -17 0Z`} fill="#3a1410" />
          <path d={`M-14 0.4 C-7 -1 7 -1 14 0.4 C8 ${Math.min(3, mouthH * 0.35)} -8 ${Math.min(3, mouthH * 0.35)} -14 0.4Z`} fill="#f2ece4" opacity={mouth > 0.12 ? 1 : 0} />
          <path d="M-18 -0.5 C-9 -4 9 -4 18 -0.5" stroke="#6b3a28" strokeWidth="2.2" strokeLinecap="round" fill="none" />
        </g>
        {/* soft highlight and brand rim light */}
        <ellipse cx="128" cy="100" rx="22" ry="12" fill="#fff" opacity="0.07" />
        <path d="M100 118 C100 70 126 54 150 54 C174 54 200 70 200 118 L200 158 C200 196 178 218 150 218 C122 218 100 196 100 158Z" fill="url(#rim)" />
      </g>
    </svg>
  );
};
