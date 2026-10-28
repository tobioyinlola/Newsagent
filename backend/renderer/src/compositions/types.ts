export type NewsProps = {
  channel: { name: string; locked: boolean };
  disclosures: { tag: string; anchor: string };
  brand: { primary: string; accent: string };
  tickerLines: string[];
  lowerThirds: { title: string; subtitle: string }[];
  anchorSrc: string | null; // transparent WebM (Option B) or full anchor clip; null renders a placeholder
  anchorDurationSeconds: number;
  // real presenter footage before and after the AI presenter (the operator's library); the studio graphics run only over the anchor
  anchorFullFrame?: boolean; // the presenter video already contains its studio: draw it full frame, not over our set
  anchorCovers?: boolean; // with anchorFullFrame: cover the picture's own screens and reflections with our boards (default true)
  studio?: string; // which set to draw (project.studio_id): "blue" (default) or "navy"
  introClip?: { src: string; seconds: number } | null;
  outroClip?: { src: string; seconds: number } | null;
  brandCards?: boolean; // open with the Cover Founder intro and close with the outro
};

export const defaultProps: NewsProps = {
  channel: { name: "Cover Founder", locked: true },
  disclosures: { tag: "Featured", anchor: "AI-generated anchor" },
  brand: { primary: "#0B3D91", accent: "#F5A623" },
  tickerLines: ["FEATURED: Acme builds tools for farmers", "Sample ticker line two"],
  lowerThirds: [{ title: "Acme", subtitle: "Featured startup" }],
  anchorSrc: null,
  anchorDurationSeconds: 10,
};

export const FPS = 30;
