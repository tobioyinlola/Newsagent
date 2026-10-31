import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const slides = [
  { label: "Tell your story", title: "A big stage for\nyour next big idea.", description: "Turn the story behind your business into a video worth sharing.", image: "/hero-studio.jpg", alt: "Cover Founder newsroom studio", tag: "YOUR STORY. IN THE SPOTLIGHT.", detail: "Video interviews", number: "01" },
  { label: "Make it news", title: "Your ambition.\nIn your own words.", description: "Bring your business journey to life with a written story and an announcement.", image: "/written-story.jpg", alt: "Editorial storytelling at Cover Founder", tag: "FROM BUSINESS STORY TO HEADLINE.", detail: "Stories & announcements", number: "02" },
  { label: "Reach further", title: "Good stories\ndeserve an audience.", description: "Choose your media outlets, distribute your announcement, and follow its progress.", image: "/boardroom.jpg", alt: "Business leaders gathered around a boardroom table", tag: "YOUR NEXT CHAPTER STARTS HERE.", detail: "Press distribution", number: "03" },
];

function UpRight() { return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M6 18 18 6M6 6h12v12" /></svg>; }

export function AuthShowcase() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [interacting, setInteracting] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setReducedMotion(query.matches);
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (paused || interacting || reducedMotion) return;
    const timer = window.setInterval(() => { if (!document.hidden) setActive(i => (i + 1) % slides.length); }, 7000);
    return () => window.clearInterval(timer);
  }, [paused, interacting, reducedMotion]);
  const slide = slides[active];
  const move = (index: number) => { setActive((index + slides.length) % slides.length); setPaused(true); };
  return <section className="auth-showcase" aria-label="Discover Cover Founder" aria-roledescription="carousel" onMouseEnter={() => setInteracting(true)} onMouseLeave={() => setInteracting(false)} onFocusCapture={() => setInteracting(true)} onBlurCapture={e => { if (!e.currentTarget.contains(e.relatedTarget)) setInteracting(false); }}>
    <div className="auth-showcase-top"><span className="auth-eyebrow"><span className="auth-live-dot" /> BUILT FOR YOUR NEXT CHAPTER</span><span className="auth-edition">CF / {slide.number}</span></div>
    <div className="auth-slide" key={active} role="group" aria-roledescription="slide" aria-label={`${active + 1} of ${slides.length}: ${slide.label}`}>
      <h1>{slide.title}</h1><p className="auth-slide-description">{slide.description}</p>
      <div className="auth-art"><img src={slide.image} alt={slide.alt} /><div className="auth-art-label"><span className="auth-art-mark">CF</span><span>{slide.tag}</span><UpRight /></div><div className="auth-art-caption"><span className="auth-caption-dot" />{slide.detail}<span>Cover Founder</span></div></div>
    </div>
    <div className="auth-carousel-controls"><div className="auth-slide-pickers" aria-label="Choose a feature">{slides.map((item, i) => <button key={item.label} type="button" aria-label={`Show ${item.label}`} aria-pressed={active === i} onClick={() => move(i)}><span /><span className="sr-only">{item.label}</span></button>)}</div><div className="auth-carousel-arrows"><span className="auth-slide-count">{slide.number} / 03</span>{!reducedMotion && <button type="button" aria-label={paused ? "Play feature carousel" : "Pause feature carousel"} onClick={() => setPaused(p => !p)}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">{paused ? <path d="m9 5 11 7-11 7Z" /> : <path d="M9 5v14M15 5v14" />}</svg></button>}<button type="button" aria-label="Previous feature" onClick={() => move(active - 1)}>←</button><button type="button" aria-label="Next feature" onClick={() => move(active + 1)}>→</button></div></div>
    <div className="auth-showcase-bottom"><p>Stories that move businesses forward.</p><Link to="/latest-stories">Explore the newsroom <UpRight /></Link></div>
  </section>;
}
