import { useState } from "react";
import { getToken } from "../lib/auth";
import { type Outlet, OUTLETS_BOTTOM, OUTLETS_TOP } from "../lib/outlets";
import { CHANNELS, CONTACT, CardArt, Cta, Eyebrow, HeroArt, Panel, SiteShell } from "./Landing";

// Dedicated page for distribution (press-distribution style): reach, how it works, coverage by region, outlet types,
// credit-based packages, the placement report and questions. Distribution is launching: the page says so plainly.

const WAITLIST = `${CONTACT}%20-%20distribution`;

const REGIONS: { name: string; places: string; outlets: string[] }[] = [
  { name: "United States", places: "National and state outlets", outlets: ["Business & finance", "Technology", "Startups & VC", "Local news"] },
  { name: "Canada", places: "National and provincial outlets", outlets: ["Business", "Technology", "Regional news"] },
  { name: "United Kingdom", places: "National and regional outlets", outlets: ["Business & finance", "Technology", "Trade press"] },
  { name: "Nigeria", places: "Lagos, Abuja and national", outlets: ["Business & finance", "Tech & startups", "National news"] },
  { name: "Kenya", places: "Nairobi and national", outlets: ["Business", "Tech & startups", "National news"] },
];

const CATEGORIES: [string, string][] = [
  ["Business & finance", "Funding rounds, results and deals."],
  ["Technology", "Launches, products and partnerships."],
  ["Startups & VC", "Founders, raises and milestones."],
  ["Regional & local news", "Stories that matter where you operate."],
  ["Trade publications", "Your industry's own press."],
  ["Social & video", `Ready for ${CHANNELS.slice(0, 4).join(", ")} and more.`],
];

const PACKAGES: { name: string; reach: string; points: string[]; featured?: boolean }[] = [
  { name: "Local", reach: "1 region", points: ["Your segment and story to one region", "Business and tech outlets", "Placement report"] },
  { name: "Regional", reach: "Up to 3 regions", points: ["Everything in Local", "Pick any three regions", "Category targeting (e.g. finance, tech)"], featured: true },
  { name: "Global", reach: "Every region", points: ["All five regions", "Full outlet categories", "Priority placement report"] },
];

const QUESTIONS: [string, string][] = [
  ["When can I use distribution?", "It's launching soon. Join the waitlist and we'll let you know first; you can make your video and story today."],
  ["How is it priced?", "With the same credits you use for videos. Each package shows its credits before you confirm, and nothing is charged until you do."],
  ["What gets distributed?", "Your news segment (video) and your written story, with your headline, links and social copy."],
  ["Which regions can I pick?", "United States, Canada, United Kingdom, Nigeria and Kenya to start, with more to follow."],
  ["Will I see where it ran?", "Yes. Every distribution comes with a placement report listing where your story appeared."],
];

function ReportMock() {
  const rows: [string, string, string][] = [["Business daily", "United States", "PUBLISHED"], ["Tech weekly", "Canada", "PUBLISHED"], ["Startup wire", "Nigeria", "PUBLISHED"], ["Finance desk", "United Kingdom", "SCHEDULED"], ["Founders' digest", "Kenya", "SCHEDULED"]];
  return (
    <Panel title="Placement report · sample" right={<span className="text-brand-green">● LIVE</span>} className="w-full max-w-md">
      <ul className="space-y-1.5">
        {rows.map(([o, r, st]) => (
          <li key={o} className="flex items-center justify-between gap-2 border-b border-white/5 pb-1"><span className="text-white">{o}</span><span className="text-white/50">{r}</span><span className={st === "PUBLISHED" ? "text-brand-green" : "text-brand-peach"}>{st}</span></li>
        ))}
      </ul>
      <p className="mt-3 text-white/40">// sample layout; real reports list real outlets</p>
    </Panel>
  );
}

// One row of outlet logos that glides sideways. The list is shown twice so the loop has no gap; the copy is hidden from screen readers.
// For people who prefer less motion the row stops and wraps into a grid instead.
function LogoRow({ outlets, reverse = false }: { outlets: Outlet[]; reverse?: boolean }) {
  const tile = (o: Outlet, hidden: boolean) => (
    <li key={`${hidden}-${o.slug}`} aria-hidden={hidden || undefined} className={`shrink-0 ${hidden ? "motion-reduce:hidden" : ""}`}>
      <img src={`/outlets/${o.slug}.webp`} alt={hidden ? "" : o.name} width={200} height={86} loading="lazy" decoding="async" draggable={false} className="h-[86px] w-[200px] rounded-lg border border-black/5 bg-white object-cover shadow-sm motion-reduce:aspect-[200/86] motion-reduce:h-auto motion-reduce:w-full" />
    </li>
  );
  return (
    <div className="overflow-hidden [mask-image:linear-gradient(to_right,transparent,#000_8%,#000_92%,transparent)] motion-reduce:[mask-image:none]">
      <ul className={`flex w-max gap-4 py-2 pr-4 motion-reduce:grid motion-reduce:w-full motion-reduce:grid-cols-3 motion-reduce:gap-2 motion-reduce:pr-0 sm:motion-reduce:grid-cols-4 lg:motion-reduce:grid-cols-6 ${reverse ? "cf-marquee-rev" : "cf-marquee"}`}>
        {outlets.map((o) => tile(o, false))}
        {outlets.map((o) => tile(o, true))}
      </ul>
    </div>
  );
}

function OutletMarquee() {
  return (
    <section aria-labelledby="outlets-h" className="border-b border-white/10 bg-ink px-4 py-16 md:px-8">
      <div className="mx-auto max-w-6xl text-center">
        <Eyebrow>Distribution channels</Eyebrow>
        <h2 id="outlets-h" className="mt-3 text-3xl text-white md:text-5xl">Outlets your story can reach.</h2>
      </div>
      <div className="cf-marquee-wrap mt-10 space-y-4 motion-reduce:mx-auto motion-reduce:max-w-6xl motion-reduce:space-y-0">
        <LogoRow outlets={OUTLETS_TOP} />
        <LogoRow outlets={OUTLETS_BOTTOM} reverse />
      </div>
    </section>
  );
}

export function DistributionPage() {
  const signedIn = Boolean(getToken());
  const [open, setOpen] = useState(QUESTIONS[0][0]);
  return (
    <SiteShell>
      <main>
        <section className="cf-grain relative overflow-hidden px-4 pb-16 pt-16 md:px-8 md:pt-24">
          <HeroArt />
          <div aria-hidden="true" className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_30%,rgba(25,26,48,0.9)_0%,rgba(25,26,48,0.6)_45%,transparent_80%)]" />
          <div className="relative z-10 mx-auto grid max-w-6xl items-center gap-10 md:grid-cols-[1.2fr_1fr]">
            <div>
              <p className="inline-block rounded-sm border border-brand-peach bg-ink/70 px-3 py-1 text-xs font-bold uppercase tracking-widest text-brand-peach">Distribution · launching soon</p>
              <h1 className="mt-6 text-4xl leading-tight text-white md:text-6xl">Your news, across <span className="text-brand-green">25K+ media platforms.</span></h1>
              <p className="mt-5 max-w-xl text-lg text-white/85">Send your news segment and written story to business, technology and regional outlets in the United States, Canada, the United Kingdom, Nigeria and Kenya. Pay with credits; get a report of where it ran.</p>
              <div className="mt-8 flex flex-wrap gap-3"><Cta href={WAITLIST} primary>Join the waitlist</Cta><Cta href="#coverage">See coverage</Cta></div>
            </div>
            <div className="flex justify-center"><ReportMock /></div>
          </div>
        </section>

        <section aria-label="Distribution in numbers" className="border-y border-white/10 bg-ink px-4 py-10 md:px-8">
          <div className="mx-auto grid max-w-6xl grid-cols-2 gap-y-6 md:grid-cols-4">
            {[["25K+", "Media platforms"], ["5", "Launch countries"], [String(CHANNELS.length), "Social & video channels"], ["1", "Credit wallet"]].map(([v, l]) => (
              <div key={l} className="px-2"><p className="text-4xl font-bold text-white md:text-5xl">{v}</p><p className="mt-1 text-xs font-bold uppercase tracking-wider text-brand-green">{l}</p></div>
            ))}
          </div>
        </section>

        <OutletMarquee />

        <section className="bg-ink px-4 py-20 md:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="text-center"><Eyebrow>How it works</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-5xl">From your newsroom to theirs.</h2></div>
            <div className="mt-10 grid border border-white/10 md:grid-cols-4">
              {[["Make your story", "Produce your news segment and feature in the AI Newsroom."], ["Choose your reach", "Pick regions and outlet categories. See the credits first."], ["We distribute", "Your video, story, headline and links go out to matching outlets."], ["Track placements", "A report shows where your story appeared."]].map(([t, d], i) => (
                <div key={t} className={`p-6 ${i < 3 ? "border-b border-white/10 md:border-b-0 md:border-r" : ""}`}><p className="text-xs font-bold text-brand-aqua">0{i + 1}</p><h3 className="mt-5 text-lg text-white">{t}</h3><p className="mt-2 text-sm text-white/70">{d}</p></div>
              ))}
            </div>
          </div>
        </section>

        <section id="coverage" className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="text-center"><Eyebrow>Coverage</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-5xl">Where your story can run.</h2></div>
            <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {REGIONS.map((r) => (
                <div key={r.name} className="rounded-sm border border-white/10 bg-white/5 p-5">
                  <h3 className="text-lg text-white">{r.name}</h3>
                  <p className="mt-1 text-xs text-white/60">{r.places}</p>
                  <ul className="mt-4 space-y-1.5 text-sm text-white/85">{r.outlets.map((o) => <li key={o} className="flex gap-2"><span className="text-brand-green" aria-hidden="true">✓</span>{o}</li>)}</ul>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="text-center"><Eyebrow>Outlet categories</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-5xl">Reach the right readers.</h2></div>
            <div className="mt-10 grid gap-px border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-3">
              {CATEGORIES.map(([t, d]) => <div key={t} className="bg-ink p-6"><h3 className="text-lg text-white">{t}</h3><p className="mt-2 text-sm text-white/70">{d}</p></div>)}
            </div>
          </div>
        </section>

        <section className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="text-center"><Eyebrow>Packages</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-5xl">Paid in credits. No subscription.</h2><p className="mx-auto mt-3 max-w-2xl text-white/70">Each package shows its credits before you confirm. Nothing is charged until you do.</p></div>
            <div className="mt-10 grid gap-4 md:grid-cols-3">
              {PACKAGES.map((p) => (
                <div key={p.name} className={`flex flex-col rounded-sm border p-6 ${p.featured ? "border-brand-green bg-white/5" : "border-white/10"}`}>
                  <p className="text-xs font-bold uppercase tracking-wider text-white/60">{p.name}</p>
                  <p className="mt-3 text-3xl font-bold text-white">{p.reach}</p>
                  <ul className="mt-5 flex-1 space-y-2 text-sm text-white/85">{p.points.map((x) => <li key={x} className="flex gap-2"><span className="text-brand-green" aria-hidden="true">✓</span>{x}</li>)}</ul>
                  <div className="mt-6"><Cta href={WAITLIST} primary={p.featured}>Join the waitlist</Cta></div>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-white/10 bg-ink px-4 py-20 md:px-8">
          <div className="mx-auto grid max-w-6xl gap-10 md:grid-cols-[1fr_2fr]">
            <div><Eyebrow>FAQ</Eyebrow><h2 className="mt-3 text-3xl text-white md:text-4xl">Distribution questions.</h2></div>
            <div className="divide-y divide-white/10 border-y border-white/10">
              {QUESTIONS.map(([q, a]) => {
                const isOpen = open === q;
                return (
                  <div key={q}>
                    <h3 className="m-0"><button type="button" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? "" : q)} className="flex w-full items-center justify-between gap-4 py-4 text-left text-base font-bold text-white hover:text-brand-green">{q}<span aria-hidden="true" className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border text-lg transition-transform ${isOpen ? "rotate-45 border-brand-green text-brand-green" : "border-white/30 text-white/70"}`}>+</span></button></h3>
                    <div hidden={!isOpen} className="pb-5 pr-10 text-white/75">{a}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="cf-stripes border-t border-white/10 px-4 py-20 text-center md:px-8">
          <div className="cf-grain relative mx-auto mb-10 h-40 max-w-4xl overflow-hidden rounded-sm"><CardArt variant="story" /></div>
          <h2 className="text-3xl text-white md:text-5xl">Be first on the wire.</h2>
          <p className="mx-auto mt-3 max-w-xl text-white/70">Join the distribution waitlist, and make your news segment in the meantime.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3"><Cta href={WAITLIST} primary>Join the waitlist</Cta>{signedIn ? <Cta to="/ai-newsroom/new">Make a video</Cta> : <Cta to="/ai-newsroom">See the AI Newsroom</Cta>}</div>
        </section>
      </main>
    </SiteShell>
  );
}
