export const STEPS = [
  { key: "draft", label: "Brief" },
  { key: "script_ready", label: "Script" },
  { key: "rendering_anchor", label: "Anchor" },
  { key: "anchor_ready", label: "Rendering" },
  { key: "final_ready", label: "Ready" },
] as const;

const LABELS: Record<string, string> = {
  draft: "Draft",
  script_ready: "Script ready for review",
  script_approved: "Script approved",
  rendering_anchor: "Recording the anchor",
  anchor_ready: "Rendering your video",
  awaiting_founder: "Waiting for founder",
  processing_founder: "Processing interview",
  merging: "Merging interview",
  final_ready: "Ready",
  failed: "Needs attention",
  limit_reached: "Paused: limit reached",
};

export const stateLabel = (s: string) => LABELS[s] ?? s;

// Which step in the progress bar is current for a given state.
export function stepIndex(state: string, failedFrom?: string): number {
  const s = state === "script_approved" ? "rendering_anchor" : state;
  const i = STEPS.findIndex((x) => x.key === s);
  if (i >= 0) return i;
  return failedFrom ? stepIndex(failedFrom) : 0;
}
