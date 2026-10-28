import { CFSymbol, Logo } from "../components/Logo";
import { getToken } from "../lib/auth";
import { CONTACT, CardArt, Cta, Eyebrow, HeroArt, Panel, SiteShell } from "./Landing";

// Dedicated page for the AI Newsroom: the team, what comes out, how a segment is made.

// A still of the on-air look: logo top-left, a name box over the headline bar, the ticker underneath.
function BroadcastMock() {
  return (
    <div className="relative mx-auto aspect-video w-full max-w-4xl overflow-hidden rounded-sm border border-white/15 bg-navy shadow-2xl">
      <svg viewBox="0 0 1600 900" className="absolute inset-0 h-full w-full" aria-hidden="true">
        <rect width="1600" height="900" fill="#14223f" />
        {[0, 1, 2, 3, 4, 5].map((i) => <rect key={i} x={i * 280 - 40} y="0" width="160" height="900" fill="#1b2e55" opacity={0.6} />)}
        <rect x="0" y="80" width="1600" height="40" fill="#2453b8" opacity="0.5" />
        <circle cx="800" cy="360" r="130" fill="#d9b49a" />
        <path d="M560 900 Q800 470 1040 900 Z" fill="#191A30" />
        <path d="M770 520 L800 900 L830 520 Z" fill="#7a1f2b" />
      </svg>
      <div className="absolute left-[2.5%] top-[4%] rounded-sm bg-navy p-1 text-brand-green"><Logo className="h-auto w-[min(9vw,84px)]" /></div>
      <div className="absolute inset-x-[3%] bottom-[11%]">
        <div className="mb-2 flex justify-end">
          <div className="border-[3px] border-brand-green bg-white px-3 py-1.5 text-ink">
            <p className="text-[min(2.6vw,20px)] font-extrabold leading-tight">Marcus</p>
            <p className="flex items-center gap-1.5 text-[min(1.5vw,12px)] font-bold uppercase"><span className="inline-block h-2 w-2 border border-ink bg-brand-green" />Presenter, Cover Founder News</p>
          </div>
        </div>
        <div className="flex border-b-4 border-brand-green">
          <div className="flex items-center gap-1.5 bg-navy px-2 text-brand-green"><CFSymbol className="h-[min(3vw,22px)] w-auto" /><span className="text-[min(1.8vw,14px)] font-extrabold">NEWS</span></div>
          <p className="flex-1 truncate bg-white px-3 py-1.5 text-[min(2.6vw,22px)] font-extrabold uppercase text-ink">Acme Farms raises $5M to bring farmers online</p>
        </div>
      </div>
      <div className="absolute inset-x-0 bottom-0 h-[8%] overflow-hidden border-t-2 border-brand-green bg-ink">
        <p className="cf-ticker w-max whitespace-nowrap px-3 pt-[0.6%] text-[min(2vw,16px)] text-white">FEATURED: Acme Farms raises $5M  •  TECH: today's technology headlines keep scrolling  •  FEATURED: Acme Farms raises $5M  •  TECH: today's technology headlines keep scrolling  •</p>
      </div>
    </div>
  );
}

const TEAM: [string, string, string][] = [
  ["AI interviewer", "Greets you by name and asks four sharp questions out loud, on camera, in about five minutes.", "INTERVIEW"],
  ["AI writer", "Turns your details and your own words into a 700–900 word feature, a social post and a headline for every answer.", "STORY"],
  ["AI presenter", "A news-desk presenter opens the segment, asks your questions and signs off. Three presenters today, more coming.", "PRESENTER"],
  ["AI editor", "Cuts your answers in full-screen, adds your name box and headline bars, captions, the ticker and your product's address.", "EDIT"],
];

const FEATURES: [string, string][] = [
  ["Broadcast graphics", "Channel logo, name boxes and headline bars in the style of a business news channel."],
  ["You, full screen", "Your answers play full frame with a headline drawn from what you said."],
  ["Live tech ticker", "Your news scrolls along the bottom, followed by today's technology headlines."],
  ["Your product's address", "Shown in the corner while the presenter signs off, so viewers can find you."],
  ["Written story included", "A detailed feature, a social post and hashtags, ready to publish."],
  ["Checked before it's made", "Claims are flagged for you to confirm; nothing that costs credits runs until you approve."],
];

export function Newsroom() {
  const signedIn = Boolean(getToken());
  return (
    <SiteShell>
      <main>
        <section className="cf-grain relative overflow-hidden px-4 pb-16 pt-16 md:px-8 md:pt-24">
          <HeroArt />
          <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_30%,rgba(25,26,48,0.9)_0%,rgba(25,26,48,0.6)_45%,transparent_80%)]" />
          <div className="relative z-10 mx-auto max-w-4xl text-center">
            <p className="inline-block rounded-sm border border-white/20 bg-ink/70 px-3 py-1 text-xs font-bold uppercase tracking-widest text-white"><span className="text-brand-green" aria-hidden="true">● </span>AI Newsroom</p>
            <h1 className="mt-6 text-4xl leading-tight text-white md:text-6xl">A full newsroom team.<br /><span className="text-brand-green">On call for your business.</span></h1>
            <p className="mx-auto mt-5 max-w-2xl text-lg text-white/85">Interviewer, writer, presenter and editor, working together to turn your announcement into a news segment and a written feature.</p>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              {signedIn ? <Cta to="/projects/new" primary>Make a video</Cta> : <Cta href={CONTACT} primary>Publish Your Story Free!</Cta>}
              <Cta href="#how">How a segment is made</Cta>
            </div>
          </div>
          <div className="relative z-10 mt-14"><BroadcastMock /></div>
        </section>

        <section className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="text-center"><Eyebrow>The team</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-5xl">Four roles. One afternoon.</h2></div>
            <div className="mt-10 grid border border-white/10 sm:grid-cols-2 lg:grid-cols-4">
              {TEAM.map(([role, text, tag], i) => (
                <div key={role} className={`p-6 ${i < TEAM.length - 1 ? "border-b border-white/10 lg:border-b-0 lg:border-r" : ""} ${i === 1 ? "sm:border-r-0 lg:border-r" : i === 0 || i === 2 ? "sm:border-r" : ""}`}>
                  <p className="text-[11px] font-bold tracking-widest text-brand-aqua">0{i + 1} · {tag}</p>
                  <h3 className="mt-5 text-xl text-white">{role}</h3>
                  <p className="mt-2 text-sm text-white/70">{text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="how" className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
          <div className="mx-auto grid max-w-6xl items-center gap-10 md:grid-cols-2">
            <div>
              <Eyebrow>How a segment is made</Eyebrow>
              <h2 className="mt-3 text-3xl text-white md:text-5xl">From details to on-air.</h2>
              <ol className="mt-8 space-y-5">
                {[["Details", "Your company, website, founder and what you're announcing."], ["AI interview", "Four questions on camera, re-record any answer."], ["Your story", "Review the feature and the presenter's words. Go back and change answers any time before you approve."], ["Your video", "Presenter clips, your answers, graphics and captions, rendered in one go."], ["Ready", "Download, share a link, post the social copy."]].map(([t, d], i) => (
                  <li key={t} className="flex gap-4"><span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 border-brand-green text-sm font-bold text-brand-green">{i + 1}</span><div><p className="font-bold text-white">{t}</p><p className="text-sm text-white/70">{d}</p></div></li>
                ))}
              </ol>
            </div>
            <div className="cf-grain relative min-h-80 overflow-hidden rounded-sm">
              <CardArt variant="video" />
              <div className="relative z-10 flex h-full min-h-80 items-center justify-center p-6">
                <Panel title="Your video" right={<span className="text-brand-green">100%</span>} className="w-full max-w-sm">
                  <ul className="space-y-1.5">{["Story approved", "Interview (4 of 4)", "Presenter: opening", "Presenter: 4 questions", "Presenter: sign-off", "Final video made and checked"].map((x) => <li key={x} className="flex justify-between"><span>{x}</span><span className="text-brand-green">DONE</span></li>)}</ul>
                </Panel>
              </div>
            </div>
          </div>
        </section>

        <section className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="text-center"><Eyebrow>What's in every segment</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-5xl">Made to look like the news.</h2></div>
            <div className="mt-10 grid gap-px border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map(([t, d]) => <div key={t} className="bg-ink p-6"><h3 className="text-lg text-white">{t}</h3><p className="mt-2 text-sm text-white/70">{d}</p></div>)}
            </div>
          </div>
        </section>

        <section className="cf-stripes border-t border-white/10 px-4 py-20 text-center md:px-8">
          <h2 className="text-3xl text-white md:text-5xl">Put your newsroom to work.</h2>
          <p className="mx-auto mt-3 max-w-xl text-white/70">Then take the story further with distribution.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">{signedIn ? <Cta to="/projects/new" primary>Make a video</Cta> : <Cta href={CONTACT} primary>Publish Your Story Free!</Cta>}<Cta to="/distribution">See distribution</Cta></div>
        </section>
      </main>
    </SiteShell>
  );
}
