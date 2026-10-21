export type NewsProps = {
  channel: { name: string; locked: boolean };
  disclosures: { tag: string; anchor: string };
  brand: { primary: string; accent: string };
  tickerLines: string[];
  lowerThirds: { title: string; subtitle: string }[];
  anchorSrc: string | null; // transparent WebM (Option B) or full anchor clip; null renders a placeholder
  anchorDurationSeconds: number;
};

export const defaultProps: NewsProps = {
  channel: { name: "Startup Spotlight Network", locked: true },
  disclosures: { tag: "Featured", anchor: "AI-generated anchor" },
  brand: { primary: "#0B3D91", accent: "#F5A623" },
  tickerLines: ["FEATURED: Acme builds tools for farmers", "Sample ticker line two"],
  lowerThirds: [{ title: "Acme", subtitle: "Featured startup" }],
  anchorSrc: null,
  anchorDurationSeconds: 10,
};

export const FPS = 30;
