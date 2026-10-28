import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Logo, SecondaryLogo } from "../components/Logo";
import { getToken } from "../lib/auth";

// The public landing page. Layout: dark site with poster-style art (sunburst, mountains, clouds) drawn in the brand palette,
// product "screens" built from real app states, and credit-based pricing read live from the packs on sale.

const CONTACT = "mailto:coverfounder@gmail.com?subject=Cover%20Founder%20access";
const P = { ink: "#222222", navy: "#191A30", green: "#C0FE73", red: "#EB464B", purple: "#634EA0", aqua: "#0CC0DF", peach: "#FFBD59", cream: "#F3EBDD" };

// ---------- poster art (inline SVG, brand colours only) ----------
function Rays({ colors, cx = 600, cy = 520, count = 18 }: { colors: string[]; cx?: number; cy?: number; count?: number }) {
  const rays = Array.from({ length: count }, (_, i) => {
    const a0 = Math.PI + (i / count) * Math.PI, a1 = Math.PI + ((i + 0.5) / count) * Math.PI;
    const r = 1600;
    return <polygon key={i} points={`${cx},${cy} ${cx + r * Math.cos(a0)},${cy + r * Math.sin(a0)} ${cx + r * Math.cos(a1)},${cy + r * Math.sin(a1)}`} fill={colors[i % colors.length]} />;
  });
  return <g>{rays}</g>;
}

function Cloud({ x, y, s = 1 }: { x: number; y: number; s?: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`} fill={P.cream}>
      <ellipse cx="0" cy="0" rx="90" ry="38" /><ellipse cx="60" cy="-22" rx="62" ry="44" /><ellipse cx="-55" cy="-14" rx="52" ry="34" /><ellipse cx="120" cy="6" rx="60" ry="28" />
    </g>
  );
}

function HeroArt() {
  return (
    <svg viewBox="0 0 1200 620" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" aria-hidden="true">
      <rect width="1200" height="620" fill={P.navy} />
      <Rays colors={[P.peach, "#2a3550", P.red, "#2a3550", P.aqua, "#2a3550"]} />
      <circle cx="600" cy="520" r="150" fill={P.peach} />
      <circle cx="600" cy="520" r="110" fill={P.red} opacity="0.9" />
      <Cloud x={130} y={360} s={1.3} /><Cloud x={1060} y={330} s={1.5} /><Cloud x={300} y={470} s={0.9} /><Cloud x={930} y={480} s={1.1} />
      <path d="M0 620 L0 470 L120 400 L210 450 L330 360 L460 470 L520 440 L600 500 L700 430 L820 480 L940 380 L1060 450 L1200 400 L1200 620 Z" fill={P.ink} opacity="0.92" />
      <path d="M0 620 L0 540 L180 500 L360 560 L600 520 L840 570 L1020 510 L1200 550 L1200 620 Z" fill={P.ink} />
    </svg>
  );
}

function BannerArt() {
  return (
    <svg viewBox="0 0 1200 420" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" aria-hidden="true">
      <rect width="1200" height="420" fill={P.aqua} />
      <Cloud x={160} y={90} s={1.1} /><Cloud x={1040} y={110} s={1.3} />
      <circle cx="600" cy="250" r="160" fill={P.peach} />
      {[P.red, P.peach, P.green, P.purple].map((c, i) => (
        <path key={c} d={`M0 ${300 + i * 26} Q600 ${200 + i * 30} 1200 ${300 + i * 26} L1200 420 L0 420 Z`} fill={c} />
      ))}
      <path d="M0 420 L0 300 L140 210 L240 270 L330 190 L420 300 L0 420 Z M1200 420 L1200 290 L1070 200 L980 260 L880 180 L780 300 L1200 420 Z" fill={P.cream} opacity="0.95" />
      <rect x="586" y="300" width="28" height="70" rx="6" fill={P.ink} /><circle cx="600" cy="288" r="14" fill={P.ink} />
    </svg>
  );
}

function CardArt({ variant }: { variant: "video" | "story" }) {
  const colors = variant === "video" ? [P.red, P.peach, P.aqua] : [P.purple, P.green, P.peach];
  return (
    <svg viewBox="0 0 600 340" preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" aria-hidden="true">
      <rect width="600" height="340" fill={P.navy} />
      <Rays colors={[...colors, "#2a3550"]} cx={300} cy={360} count={14} />
      <Cloud x={90} y={250} s={0.8} /><Cloud x={520} y={240} s={0.9} />
      <path d="M0 340 L0 280 L120 250 L240 290 L360 240 L480 285 L600 255 L600 340 Z" fill={P.ink} />
    </svg>
  );
}

// ---------- small building blocks ----------
function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-brand-green"><span aria-hidden="true">● </span>{children}</p>;
}

function Panel({ title, right, children, className = "" }: { title: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-sm border border-white/10 bg-[#141522]/95 p-3 font-mono text-[11px] text-white/80 shadow-2xl ${className}`}>
      <div className="mb-2 flex items-center justify-between uppercase tracking-wider text-white/50"><span>{title}</span>{right}</div>
      {children}
    </div>
  );
}

const Live = ({ children = "LIVE" }: { children?: ReactNode }) => <span className="text-brand-green"><span aria-hidden="true">● </span>{children}</span>;

function Cta({ to, href, children, primary = false }: { to?: string; href?: string; children: ReactNode; primary?: boolean }) {
  const cls = primary
    ? "inline-flex items-center gap-2 rounded-sm border-2 border-brand-green bg-brand-green px-5 py-3 text-sm font-bold text-ink hover:bg-transparent hover:text-brand-green"
    : "inline-flex items-center gap-2 rounded-sm border-2 border-white/60 px-5 py-3 text-sm font-bold text-white hover:border-brand-green hover:text-brand-green";
  return to ? <Link to={to} className={cls}>{children}</Link> : <a href={href} className={cls}>{children}</a>;
}

// ---------- the product "screen" in the hero (mirrors the real app) ----------
function StudioMock() {
  return (
    <div className="relative z-10 mx-auto grid max-w-5xl gap-3 rounded-sm border border-white/10 bg-ink/95 p-3 text-left md:grid-cols-[1fr_1.6fr_1fr]">
      <div className="col-span-full flex items-center justify-between rounded-sm bg-white/5 px-3 py-2 font-mono text-xs text-white/60">
        <span>coverfounder // <span className="text-white">studio</span></span><Live>ON AIR</Live>
      </div>
      <Panel title="AI interview" right={<span>4 / 4</span>}>
        <ol className="space-y-2">
          {["What are you launching today?", "Who has this problem, and how badly?", "How does it work, in plain words?", "What comes next for the company?"].map((q, i) => (
            <li key={q} className="flex gap-2"><span className="text-brand-green">✓</span><span><span className="text-white/40">Q{i + 1} </span>{q}</span></li>
          ))}
        </ol>
        <p className="mt-3 text-white/40">// about 5 minutes, on camera</p>
      </Panel>
      <div className="relative overflow-hidden rounded-sm border border-white/10 bg-navy">
        <svg viewBox="0 0 480 270" className="block w-full" aria-hidden="true">
          <rect width="480" height="270" fill="#1d2a4a" />
          <rect x="0" y="150" width="480" height="120" fill="#16213b" />
          <rect x="300" y="40" width="150" height="90" fill="#26365e" stroke={P.aqua} strokeWidth="2" />
          <text x="375" y="92" textAnchor="middle" fontFamily="Inter" fontSize="16" fontWeight="700" fill={P.green}>LAUNCH</text>
          <circle cx="170" cy="105" r="34" fill="#e7c2a0" /><path d="M110 230 Q170 140 230 230 Z" fill={P.ink} /><rect x="60" y="200" width="240" height="40" fill="#0f1730" />
          <rect x="0" y="196" width="300" height="34" fill={P.green} /><text x="12" y="218" fontFamily="Inter" fontSize="14" fontWeight="700" fill={P.ink}>ACME FARMS RAISES SEED ROUND</text>
          <rect x="0" y="246" width="480" height="24" fill={P.ink} /><text x="12" y="263" fontFamily="Inter" fontSize="12" fill="#fff">FEATURED: Acme Farms helps growers sell direct  •  Founder interview inside  •</text>
          <rect x="14" y="12" width="118" height="22" fill="rgba(14,22,44,.8)" /><text x="22" y="28" fontFamily="Inter" fontSize="12" fontWeight="700" fill="#fff">COVER FOUNDER</text>
        </svg>
      </div>
      <Panel title="Your video" right={<span className="text-brand-green">89%</span>}>
        <ul className="space-y-1.5">
          {[["Story approved", "done"], ["Interview", "done"], ["Presenter: opening", "done"], ["Presenter: 4 questions", "done"], ["Presenter: sign-off", "done"], ["Final video", "working"]].map(([t, s]) => (
            <li key={t} className="flex items-center justify-between"><span>{t}</span>{s === "done" ? <span className="rounded-sm border border-white/15 px-1.5 text-white/60">DONE</span> : <span className="rounded-sm border border-brand-peach px-1.5 text-brand-peach">RENDERING</span>}</li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

// ---------- sections ----------
const USE_CASES = [
  { key: "launch", label: "Product launch", icon: "▶", title: "Launch day, on the news", body: "Tell us what you're shipping. Our AI interviewer asks the questions a reporter would, you answer on camera, and the presenter builds the segment around your own words.", points: ["Presenter-led opening that sets up the launch", "Your answers, cut in beside the presenter", "Product address on screen during the sign-off", "Captions and a ready-to-post social caption"] },
  { key: "funding", label: "Funding round", icon: "◆", title: "Announce the round with context", body: "Investors, customers and hires want the why, not just the number. The written story explains the problem, the product and what the money is for, and flags anything you didn't disclose.", points: ["A full written feature, 700 to 900 words", "\"What the company hasn't said\" kept honest", "Claims you make are checked before publishing", "One video, one story, one post"] },
  { key: "partnership", label: "Partnership", icon: "✚", title: "Two companies, one story", body: "Explain what the partnership means for customers in plain language, with a founder on camera explaining it in their own voice.", points: ["Questions written for your announcement type", "Pick which answers make the cut", "Natural presenter sign-off", "Shareable link for partners"] },
  { key: "hiring", label: "Hiring", icon: "●", title: "Recruit with a story, not a job post", body: "Candidates want to hear from the founder. Turn a hiring push into a short news segment about the mission and the team you're building.", points: ["Founder answers, on camera", "Written story for your careers page", "Social copy for LinkedIn and X", "Ready the same day"] },
  { key: "milestone", label: "Milestone", icon: "★", title: "Make the milestone count", body: "A customer number, a new market, a year in business. Give it the weight of a news segment, with the details that make it credible.", points: ["Detailed story with the numbers you confirm", "Founder interview for the human side", "Thumbnail and captions included", "Your brand colours in the graphics"] },
] as const;

function UseCases() {
  const [tab, setTab] = useState<string>(USE_CASES[0].key);
  const u = USE_CASES.find((x) => x.key === tab)!;
  return (
    <section id="use-cases" className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="text-center">
          <Eyebrow>Built for</Eyebrow>
          <h2 className="mt-3 text-3xl text-white md:text-5xl">Every announcement worth telling.</h2>
          <p className="mt-3 text-white/70">Whatever you're announcing, we handle the newsroom part.</p>
        </div>
        <div role="tablist" aria-label="Announcement types" className="mt-10 grid grid-cols-2 border border-white/10 sm:grid-cols-3 md:grid-cols-5">
          {USE_CASES.map((x) => (
            <button key={x.key} role="tab" aria-selected={tab === x.key} onClick={() => setTab(x.key)}
              className={`flex items-center justify-center gap-2 border-white/10 px-3 py-4 text-sm font-bold md:border-r ${tab === x.key ? "border-b-2 !border-b-brand-green bg-white/5 text-brand-green" : "text-white/70 hover:text-white"}`}>
              <span aria-hidden="true">{x.icon}</span>{x.label}
            </button>
          ))}
        </div>
        <div role="tabpanel" className="grid border border-t-0 border-white/10 md:grid-cols-2">
          <div className="p-6 md:p-10">
            <h3 className="text-2xl text-white">{u.title}</h3>
            <p className="mt-3 text-white/70">{u.body}</p>
            <ul className="mt-6 space-y-3">{u.points.map((p) => <li key={p} className="flex gap-3 text-white/90"><span className="text-brand-green" aria-hidden="true">✓</span>{p}</li>)}</ul>
            <div className="mt-8"><Cta href={CONTACT} primary>Request access</Cta></div>
          </div>
          <div className="cf-grain relative min-h-72 overflow-hidden">
            <CardArt variant={u.key === "funding" || u.key === "milestone" ? "story" : "video"} />
            <div className="relative z-10 flex h-full items-center justify-center p-6">
              <Panel title={`${u.label} · plan`} right={<Live>OK</Live>} className="w-full max-w-sm">
                <ul className="space-y-1.5">
                  {[["Interview questions", "4"], ["Answers featured", "4 of 4"], ["Story length", "~800 words"], ["Formats", "16:9 + captions"]].map(([a, b]) => (
                    <li key={a} className="flex justify-between border-b border-white/5 pb-1"><span>{a}</span><span className="text-brand-green">{b}</span></li>
                  ))}
                </ul>
              </Panel>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function TwoWays() {
  const cards = [
    { art: "video" as const, title: "The news segment", body: "A broadcast-style video with an AI presenter, your founder's own answers cut in beside them, on-screen graphics in your colours, a natural sign-off and your product's address in the corner.", tags: ["AI PRESENTER", "FOUNDER ANSWERS", "CAPTIONS"] },
    { art: "story" as const, title: "The written story", body: "A detailed feature written from your details and your interview: the news, the problem, how it works, what you said and what's next, plus a social post and hook ready to publish.", tags: ["FEATURE", "SOCIAL POST", "FACT FLAGS"] },
  ];
  return (
    <section id="features" className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="text-center"><Eyebrow>What you get</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-5xl">Two ways to tell it.</h2><p className="mt-3 text-white/70">One for watching. One for reading. Both from a single interview.</p></div>
        <div className="mt-10 grid border border-white/10 md:grid-cols-2">
          {cards.map((c, i) => (
            <div key={c.title} className={`p-6 md:p-8 ${i === 0 ? "md:border-r md:border-white/10" : ""}`}>
              <div className="cf-grain relative h-56 overflow-hidden rounded-sm">
                <CardArt variant={c.art} />
                <div className="relative z-10 flex h-full items-end p-4">
                  <div className="flex flex-wrap gap-2">{c.tags.map((t) => <span key={t} className="rounded-sm border border-brand-green bg-ink/80 px-2 py-1 font-mono text-[11px] font-bold text-brand-green">{t}</span>)}</div>
                </div>
              </div>
              <h3 className="mt-6 text-2xl text-white">{c.title}</h3>
              <p className="mt-2 text-white/70">{c.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Banner() {
  const facts = [["~5 min", "on-camera AI interview"], ["4", "questions, every answer can feature"], ["700+", "words in your written story"], ["1", "credit wallet for everything"]];
  return (
    <section className="border-t border-white/10 bg-ink px-4 pt-20 md:px-8">
      <div className="mx-auto max-w-6xl text-center">
        <h2 className="text-3xl text-white md:text-5xl">A newsroom for businesses,<br />without the newsroom.</h2>
        <p className="mx-auto mt-4 max-w-2xl text-white/70">You bring the news and twenty minutes. We bring the presenter, the questions, the writer, the edit and the graphics, and label every AI-generated presenter clearly.</p>
        <div className="mt-6 flex justify-center gap-3"><Cta href={CONTACT} primary>Get started</Cta><Cta href="#pricing">See pricing</Cta></div>
      </div>
      <div className="cf-grain relative mx-auto mt-12 h-64 max-w-6xl overflow-hidden md:h-96"><BannerArt /></div>
      <div className="mx-auto grid max-w-6xl grid-cols-2 border border-t-0 border-white/10 md:grid-cols-4">
        {facts.map(([n, t], i) => (
          <div key={t} className={`p-6 ${i % 2 === 0 ? "border-r border-white/10" : "md:border-r md:border-white/10"} ${i < 2 ? "border-b border-white/10 md:border-b-0" : ""}`}>
            <p className="font-mono text-4xl font-bold text-white">{n}</p>
            <p className="mt-1 font-mono text-[11px] uppercase tracking-wider text-white/60">{t}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function HowItWorks() {
  const steps = [
    ["01", "Your details", "Company, founder, website and what you're announcing. Two minutes."],
    ["02", "AI interview", "Our interviewer greets you by name and asks four questions out loud. You answer on camera."],
    ["03", "Story & pictures", "We write the feature and the social post from what you said. You check it and add two or three pictures."],
    ["04", "Your video", "The presenter records the opening, the questions and the sign-off; we cut your answers in and render it."],
  ];
  return (
    <section id="how" className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="text-center"><Eyebrow>How it works</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-5xl">From details to on-air<br />in four steps.</h2><p className="mx-auto mt-3 max-w-2xl text-white/70">One founder presses go. The platform writes the questions, runs the interview, writes the story, records the presenter and edits the segment.</p></div>
        <div className="mt-10 border border-white/10">
          <div className="grid md:grid-cols-4">
            {steps.map(([n, t, d], i) => (
              <div key={n} className={`p-6 ${i < 3 ? "border-b border-white/10 md:border-b-0 md:border-r" : ""}`}>
                <p className="font-mono text-xs text-brand-aqua">{n}</p><h3 className="mt-6 text-lg text-white">{t}</h3><p className="mt-2 text-sm text-white/70">{d}</p>
              </div>
            ))}
          </div>
          <div className="cf-grid-lines hidden items-center justify-between gap-4 border-t border-white/10 bg-[#1b1c22] px-8 py-10 md:flex">
            <div className="flex flex-col items-center gap-2 font-mono text-[11px] text-white/60"><div className="flex h-14 w-14 items-center justify-center rounded-sm border border-brand-green text-2xl text-brand-green" aria-hidden="true">☺</div>1 FOUNDER</div>
            <span className="text-white/30" aria-hidden="true">→</span>
            <Panel title="Newsroom pipeline" className="w-56">{["AI writes questions", "AI interviews you", "AI writes the story", "Presenter records"].map((x) => <p key={x} className="mt-1 rounded-sm border border-white/10 px-2 py-1">{x}</p>)}</Panel>
            <span className="text-white/30" aria-hidden="true">→</span>
            <Panel title="Edit & render" className="w-56">{["Answers cut in", "Brand graphics", "Captions", "Quality check"].map((x) => <p key={x} className="mt-1 flex justify-between rounded-sm border border-white/10 px-2 py-1">{x}<span className="text-brand-green">OK</span></p>)}</Panel>
            <span className="text-white/30" aria-hidden="true">→</span>
            <Panel title="Ready to share" className="w-56">{["Video (16:9)", "Written story", "Social post", "Share link"].map((x) => <p key={x} className="mt-1 flex items-center gap-2 rounded-sm border border-white/10 px-2 py-1"><span className="text-brand-red" aria-hidden="true">▶</span>{x}</p>)}</Panel>
          </div>
        </div>
      </div>
    </section>
  );
}

function Distribution() {
  const regions = ["North America", "Europe", "Africa", "South America", "Asia-Pacific", "Middle East"];
  return (
    <section id="distribution" className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
      <div className="mx-auto grid max-w-6xl items-center gap-10 md:grid-cols-2">
        <div>
          <Eyebrow>Distribution · coming soon</Eyebrow>
          <h2 className="mt-3 text-3xl text-white md:text-5xl">Take your news across borders.</h2>
          <p className="mt-4 text-white/70">Businesses in one market rarely reach the next. Distribution will place your segment and story with audiences in the regions you choose, paid for with the same credits you use to make the video.</p>
          <ul className="mt-6 space-y-3 text-white/90">
            {["Pick one region or several for each announcement", "Credits per region, shown before you confirm", "Your video and story stay yours to share anywhere"].map((x) => <li key={x} className="flex gap-3"><span className="text-brand-green" aria-hidden="true">✓</span>{x}</li>)}
          </ul>
          <div className="mt-8"><Cta href={`${CONTACT}%20-%20distribution`} primary>Join the distribution waitlist</Cta></div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {regions.map((r, i) => (
            <div key={r} className="rounded-sm border border-white/10 bg-white/5 p-4">
              <p className="font-mono text-[11px] text-white/50">REGION 0{i + 1}</p>
              <p className="mt-2 font-bold text-white">{r}</p>
              <p className="mt-3 inline-block rounded-sm border border-brand-peach px-2 py-0.5 font-mono text-[11px] text-brand-peach">COMING SOON</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Pricing() {
  const packs = useQuery({ queryKey: ["public-packs"], queryFn: () => unwrap(api.GET("/v1/public/packs")), retry: false, staleTime: 600000 });
  const list = packs.data ?? [];
  const uses = [["Make a video", "Credits cover the presenter, the interview transcription and the render. You see the cost before anything is made."], ["Written story & social post", "Included with every video you make."], ["Distribution", "Credits per region you choose. Coming soon."]];
  return (
    <section id="pricing" className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="text-center"><Eyebrow>Pricing</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-5xl">Buy credits. Spend them on news.</h2><p className="mx-auto mt-3 max-w-2xl text-white/70">No subscription. Top up a credit wallet and use it to make videos and, soon, to distribute them. Failed steps are never charged.</p></div>
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {list.length ? list.map((p, i) => (
            <div key={p.id} className={`rounded-sm border p-6 ${i === Math.min(1, list.length - 1) ? "border-brand-green bg-white/5" : "border-white/10"}`}>
              <p className="font-mono text-xs uppercase tracking-wider text-white/60">{p.name}</p>
              <p className="mt-4 font-mono text-4xl font-bold text-white">${Number(p.price_usd).toLocaleString()}</p>
              <p className="mt-1 text-brand-green">{Number(p.credits).toLocaleString()} credits</p>
              <div className="mt-6"><Cta href={CONTACT} primary={i === Math.min(1, list.length - 1)}>Get started</Cta></div>
            </div>
          )) : (
            <div className="rounded-sm border border-white/10 p-6 md:col-span-3 text-center">
              <p className="text-white">{packs.isLoading ? "Loading credit packs…" : "Credit packs are set up with you when you join."}</p>
              {!packs.isLoading && <div className="mt-4"><Cta href={CONTACT} primary>Talk to us</Cta></div>}
            </div>
          )}
        </div>
        <div className="mt-6 grid border border-white/10 md:grid-cols-3">
          {uses.map(([t, d], i) => <div key={t} className={`p-6 ${i < 2 ? "border-b border-white/10 md:border-b-0 md:border-r" : ""}`}><h3 className="text-base text-white">{t}</h3><p className="mt-2 text-sm text-white/70">{d}</p></div>)}
        </div>
      </div>
    </section>
  );
}

const FAQ: { group: string; items: [string, string][] }[] = [
  { group: "The product", items: [
    ["What exactly do I get?", "A broadcast-style news video with an AI presenter and your founder's answers cut in, a detailed written story (700 to 900 words), a social post with a hook and hashtags, captions and a thumbnail. All from one short interview."],
    ["Is the presenter a real person?", "No. The presenter is AI-generated and every video says so on screen. The founder's answers are real: your own recording, never rewritten or re-voiced."],
    ["How long does it take?", "About two minutes for your details and five for the interview. The written story is ready within a minute or two; the video usually follows within the hour."],
    ["Can I check everything before it's made?", "Yes. You review the written story and the presenter's words, choose which answers go in, and nothing that costs credits runs until you approve."],
  ] },
  { group: "The interview", items: [
    ["Do I need a studio or equipment?", "No. A laptop or phone with a camera, a quiet room and a decent connection. The interview runs in your browser; nothing to install."],
    ["What will I be asked?", "Four questions written for your announcement: what's new, who it's for, how it works and what comes next. You see them before you start."],
    ["What if I stumble on an answer?", "Record it again. Only the take you keep is used, and you pick which answers appear in the video."],
  ] },
  { group: "Credits & access", items: [
    ["How does pricing work?", "You buy a pack of credits and spend them as you make videos. There's no subscription, and a step that fails is never charged."],
    ["What is distribution?", "Coming soon: placing your segment and story with audiences in the regions you choose (North America, Europe, Africa, South America, Asia-Pacific, the Middle East), paid per region in credits."],
    ["Who can sign up?", "Cover Founder is invite-only while we grow. Request access and we'll email you an invitation link; it stays valid for at least 48 hours."],
    ["Who owns the video?", "You do. Download it, post it anywhere, or share a private link."],
  ] },
];

function Faq() {
  const [open, setOpen] = useState<string>(FAQ[0].items[0][0]);
  return (
    <section id="faq" className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
      <div className="mx-auto grid max-w-6xl gap-10 md:grid-cols-[1fr_2fr]">
        <div>
          <Eyebrow>FAQ</Eyebrow>
          <h2 className="mt-3 text-3xl text-white md:text-4xl">Questions, answered.</h2>
          <p className="mt-3 text-white/70">Everything businesses ask before their first segment. Something else on your mind?</p>
          <a href="mailto:coverfounder@gmail.com" className="mt-5 inline-flex items-center gap-2 font-bold text-brand-green hover:underline">Ask us directly <span aria-hidden="true">→</span></a>
        </div>
        <div className="space-y-8">
          {FAQ.map((g) => (
            <div key={g.group}>
              <p className="mb-2 font-mono text-xs font-bold uppercase tracking-[0.2em] text-brand-peach">{g.group}</p>
              <div className="divide-y divide-white/10 border-y border-white/10">
                {g.items.map(([q, a]) => {
                  const isOpen = open === q;
                  const id = `faq-${q.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;
                  return (
                    <div key={q}>
                      <h3 className="m-0">
                        <button type="button" aria-expanded={isOpen} aria-controls={id} onClick={() => setOpen(isOpen ? "" : q)}
                          className="flex w-full items-center justify-between gap-4 py-4 text-left font-sans text-base font-bold text-white hover:text-brand-green">
                          {q}
                          <span aria-hidden="true" className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border text-lg transition-transform ${isOpen ? "rotate-45 border-brand-green text-brand-green" : "border-white/30 text-white/70"}`}>+</span>
                        </button>
                      </h3>
                      <div id={id} hidden={!isOpen} className="pb-5 pr-10 text-white/75">{a}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function Footer() {
  const cols: { title: string; links: [string, string][] }[] = [
    { title: "Product", links: [["Use cases", "#use-cases"], ["How it works", "#how"], ["Distribution", "#distribution"], ["Pricing", "#pricing"], ["FAQ", "#faq"]] },
    { title: "Members", links: [["Sign in", "/login"], ["Reset password", "/forgot"], ["Request access", CONTACT], ["Contact support", "mailto:coverfounder@gmail.com"]] },
    { title: "Trust", links: [["AI disclosure", "#faq"], ["Your data", "/account"], ["Security", "/security"]] },
  ];
  const link = (label: string, href: string) => href.startsWith("/")
    ? <Link to={href} className="text-white/80 hover:text-brand-green">{label}</Link>
    : <a href={href} className="text-white/80 hover:text-brand-green">{label}</a>;
  return (
    <footer className="relative overflow-hidden border-t border-white/10 bg-navy px-4 pt-14 md:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="grid grid-cols-2 gap-10 border-t border-white/15 pt-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div className="col-span-2 md:col-span-1">
            <Logo className="h-auto w-[200px] text-brand-green" />
            <p className="mt-5 max-w-xs text-white/80">The AI newsroom for businesses. Your announcement, told like news, in your own words.</p>
          </div>
          {cols.map((c) => (
            <nav key={c.title} aria-label={c.title}>
              <p className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-brand-peach">{c.title}</p>
              <ul className="mt-4 space-y-2.5">{c.links.map(([l, h]) => <li key={l}>{link(l, h)}</li>)}</ul>
            </nav>
          ))}
        </div>
        <div className="mt-12 flex flex-wrap items-center justify-between gap-3 text-xs text-white/60">
          <p className="font-bold">© {new Date().getFullYear()} Cover Founder. All rights reserved.</p>
          <p className="max-w-lg">Every Cover Founder video uses an AI-generated presenter and is labelled as such. Founder answers are the founder's own recordings.</p>
        </div>
      </div>
      <p aria-hidden="true" className="pointer-events-none mt-6 select-none whitespace-nowrap bg-gradient-to-b from-white/35 to-transparent bg-clip-text text-center font-mono text-[11vw] font-bold leading-[0.85] text-transparent md:text-[9.5rem]">COVER FOUNDER</p>
    </footer>
  );
}

const NAV: [string, string][] = [["Use cases", "#use-cases"], ["How it works", "#how"], ["Distribution", "#distribution"], ["Pricing", "#pricing"], ["FAQ", "#faq"]];

// Phones and tablets: the site menu slides in from the right edge over a dimmed page. Esc, the scrim, Close or any link closes it.
function MobileMenu({ open, onClose, signedIn }: { open: boolean; onClose: () => void; signedIn: boolean }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden"; // the page behind doesn't scroll while the menu is open
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);
  return (
    <div className="md:hidden">
      <div aria-hidden="true" onClick={onClose} className={`fixed inset-0 z-50 bg-ink/70 transition-opacity duration-200 ${open ? "opacity-100" : "pointer-events-none opacity-0"}`} />
      <div id="site-menu" role="dialog" aria-modal="true" aria-label="Menu" className={`fixed inset-y-0 right-0 z-50 flex w-80 max-w-[85vw] flex-col border-l border-white/10 bg-ink p-5 transition-transform duration-200 ${open ? "translate-x-0" : "invisible translate-x-full"}`}>
        <div className="flex items-center justify-between">
          <span className="font-mono text-lg font-bold text-white">Menu</span>
          <button type="button" onClick={onClose} className="rounded-sm border-2 border-brand-green px-3 py-1.5 text-sm font-bold text-brand-green">Close</button>
        </div>
        <nav aria-label="Site (mobile)" className="mt-6 flex flex-col">
          {NAV.map(([l, h]) => <a key={h} href={h} onClick={onClose} className="border-b border-white/10 py-4 text-lg font-bold text-white hover:text-brand-green">{l}</a>)}
        </nav>
        <div className="mt-auto flex flex-col gap-3 pt-6">
          {signedIn ? <Link to="/dashboard" onClick={onClose} className="rounded-sm border-2 border-brand-green bg-brand-green px-4 py-3 text-center font-bold text-ink">Dashboard</Link> : (
            <>
              <a href={CONTACT} onClick={onClose} className="rounded-sm border-2 border-brand-green bg-brand-green px-4 py-3 text-center font-bold text-ink">Request access</a>
              <Link to="/login" onClick={onClose} className="rounded-sm border-2 border-white/60 px-4 py-3 text-center font-bold text-white">Sign in</Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function Landing() {
  const signedIn = Boolean(getToken());
  const [menu, setMenu] = useState(false);
  const closeMenu = useCallback(() => setMenu(false), []);
  const ticker = "FEATURED: Your launch, told like news  •  AI interview in your browser  •  Written story and social post included  •  Credits, no subscription  •  ";
  return (
    <div className="min-h-screen bg-ink text-white">
      <header className="sticky top-0 z-40 border-b border-white/10 bg-ink/95 backdrop-blur">
        <nav aria-label="Site" className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 md:px-8">
          <Link to="/" className="flex items-center gap-2 text-brand-green" aria-label="Cover Founder home"><SecondaryLogo className="h-9 w-auto" /></Link>
          <div className="hidden items-center gap-6 text-sm text-white/80 md:flex">
            {NAV.map(([l, h]) => <a key={h} href={h} className="hover:text-brand-green">{l}</a>)}
          </div>
          <div className="flex items-center gap-2">
            {signedIn ? <Link to="/dashboard" className="rounded-sm border-2 border-brand-green bg-brand-green px-3 py-2 text-sm font-bold text-ink">Dashboard</Link> : (
              <><Link to="/login" className="rounded-sm border-2 border-white/60 px-3 py-2 text-sm font-bold hover:border-brand-green hover:text-brand-green">Sign in</Link>
              <a href={CONTACT} className="hidden rounded-sm border-2 border-brand-green bg-brand-green px-3 py-2 text-sm font-bold text-ink sm:inline-block">Request access</a></>
            )}
            <button type="button" onClick={() => setMenu(true)} aria-expanded={menu} aria-controls="site-menu" aria-label="Open menu" className="flex h-10 w-10 items-center justify-center rounded-sm border-2 border-brand-green text-brand-green md:hidden">
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
            </button>
          </div>
        </nav>
      </header>
      <MobileMenu open={menu} onClose={closeMenu} signedIn={signedIn} />

      <main>
        <section className="cf-grain relative overflow-hidden px-4 pb-16 pt-16 md:px-8 md:pt-24">
          <HeroArt />
          <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_30%,rgba(25,26,48,0.88)_0%,rgba(25,26,48,0.55)_45%,transparent_75%)]" />
          <div className="relative z-10 mx-auto max-w-4xl text-center">
            <p className="inline-block rounded-sm border border-white/20 bg-ink/70 px-3 py-1 font-mono text-xs font-bold uppercase tracking-widest text-white"><span className="text-brand-green" aria-hidden="true">● </span>AI newsroom for businesses</p>
            <h1 className="mt-6 text-4xl leading-tight text-white md:text-6xl">Your launch, on the news.<br /><span className="text-brand-green">Told in your own words.</span></h1>
            <p className="mx-auto mt-5 max-w-2xl text-lg text-white/85">An AI interviewer, an AI presenter and a newsroom writer turn your announcement into a broadcast-style video and a full written story, in one afternoon.</p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              {signedIn ? <Cta to="/projects/new" primary>Make a video</Cta> : <Cta href={CONTACT} primary>Request access</Cta>}
              <Cta href="#how">See how it works</Cta>
            </div>
          </div>
          <div className="relative z-10 mt-14"><StudioMock /></div>
        </section>
        <div className="overflow-hidden border-y border-brand-green/40 bg-ink py-3" aria-hidden="true">
          <div className="cf-ticker flex w-max whitespace-nowrap font-mono text-sm text-white/80"><span>{ticker.repeat(4)}</span><span>{ticker.repeat(4)}</span></div>
        </div>
        <UseCases />
        <TwoWays />
        <Banner />
        <HowItWorks />
        <Distribution />
        <Pricing />
        <Faq />
        <section className="cf-stripes border-t border-white/10 px-4 py-20 text-center md:px-8">
          <h2 className="text-3xl text-white md:text-5xl">Ready to go on air?</h2>
          <p className="mx-auto mt-3 max-w-xl text-white/70">Tell us about your next announcement. We'll send you an invitation and your first credits.</p>
          <div className="mt-8 flex justify-center gap-3">{signedIn ? <Cta to="/projects/new" primary>Make a video</Cta> : <Cta href={CONTACT} primary>Request access</Cta>}<Cta to="/login">Sign in</Cta></div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
