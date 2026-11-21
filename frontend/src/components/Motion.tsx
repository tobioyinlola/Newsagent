import { LazyMotion, domAnimation, m, useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";

// Small, calm motion for the public pages. Everything is skipped for visitors who ask for reduced motion,
// and content is always in the page (it only fades and rises), so nothing is hidden if a script is slow.
const EASE = [0.22, 1, 0.36, 1] as const;

export function MotionRoot({ children }: { children: ReactNode }) {
  return <LazyMotion features={domAnimation} strict>{children}</LazyMotion>;
}

/** Fades up once when it scrolls into view. */
export function Reveal({ children, delay = 0, y = 18, className, as = "div" }: { children: ReactNode; delay?: number; y?: number; className?: string; as?: "div" | "li" | "section" }) {
  const reduce = useReducedMotion();
  const Tag = m[as];
  if (reduce) return <Tag className={className}>{children}</Tag>;
  return (
    <Tag className={className} initial={{ opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "0px 0px -8% 0px" }} transition={{ duration: 0.6, delay, ease: EASE }}>
      {children}
    </Tag>
  );
}

/** Hero entrance: runs once on load, one piece after another. */
export function Rise({ children, order = 0, className }: { children: ReactNode; order?: number; className?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return <m.div className={className} initial={{ opacity: 0, y: 22 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, delay: 0.1 + order * 0.12, ease: EASE }}>{children}</m.div>;
}

/** A line that draws itself left to right when it comes into view. */
export function DrawLine({ className }: { className?: string }) {
  const reduce = useReducedMotion();
  return <m.div aria-hidden="true" className={`origin-left ${className ?? ""}`} initial={{ scaleX: reduce ? 1 : 0 }} whileInView={{ scaleX: 1 }} viewport={{ once: true, margin: "0px 0px -15% 0px" }} transition={{ duration: 1.2, ease: EASE }} />;
}

/** Counts up to a number such as "1.2K" or "2,500+" when it scrolls into view; anything else is shown as it is. */
export function CountUp({ value }: { value: string }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -10% 0px" });
  const hit = /^(\d[\d,]*(?:\.\d+)?)(.*)$/.exec(value);
  const target = hit ? parseFloat(hit[1].replace(/,/g, "")) : NaN;
  const [shown, setShown] = useState<number | null>(null);
  useEffect(() => {
    if (!inView || reduce || Number.isNaN(target)) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 1200);
      setShown(target * (1 - Math.pow(1 - t, 3)));
      if (t < 1) raf = requestAnimationFrame(tick); else setShown(null);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, reduce, target]);
  if (!hit || shown === null) return <span ref={ref}>{value}</span>;
  const decimals = hit[1].includes(".") ? hit[1].split(".")[1].length : 0;
  const text = shown.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return <span ref={ref} aria-label={value}>{text}{hit[2]}</span>;
}
