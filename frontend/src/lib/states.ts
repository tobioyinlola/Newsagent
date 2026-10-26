export type Step = { label: string; states: string[] };

// The progress bar differs when a founder interview is included.
export const stepsFor = (interview: boolean, mode: string = "invite"): Step[] =>
  interview && mode === "live"
    ? [
        { label: "Announcement", states: ["draft"] },
        { label: "Script", states: ["script_ready"] },
        { label: "Interview", states: ["script_approved", "interviewing"] },
        { label: "AI presenter", states: ["rendering_anchor", "anchor_ready"] },
        { label: "Final video", states: ["merging"] },
        { label: "Ready", states: ["final_ready"] },
      ]
    : interview
    ? [
        { label: "Brief", states: ["draft"] },
        { label: "Script", states: ["script_ready"] },
        { label: "Anchor", states: ["script_approved", "rendering_anchor", "anchor_ready"] },
        { label: "Founder", states: ["awaiting_founder"] },
        { label: "Review", states: ["processing_founder"] },
        { label: "Final video", states: ["merging"] },
        { label: "Ready", states: ["final_ready"] },
      ]
    : [
        { label: "Brief", states: ["draft"] },
        { label: "Script", states: ["script_ready"] },
        { label: "Anchor", states: ["script_approved", "rendering_anchor"] },
        { label: "Rendering", states: ["anchor_ready"] },
        { label: "Ready", states: ["final_ready"] },
      ];

const LABELS: Record<string, string> = {
  draft: "Draft",
  script_ready: "Script ready for review",
  script_approved: "Script approved",
  interviewing: "Your AI interview",
  rendering_anchor: "Recording the anchor",
  anchor_ready: "Rendering your video",
  awaiting_founder: "Waiting for your founder",
  processing_founder: "Founder answers ready to review",
  merging: "Making the final video",
  final_ready: "Ready",
  failed: "Needs attention",
  limit_reached: "Paused: limit reached",
  cancelled: "Cancelled",
};

export const stateLabel = (s: string) => LABELS[s] ?? s;

// Index of the current step. A failed/paused project shows the step it stopped at.
export function stepIndex(steps: Step[], state: string, failedFrom?: string): number {
  const i = steps.findIndex((s) => s.states.includes(state));
  if (i >= 0) return i;
  return failedFrom ? stepIndex(steps, failedFrom) : 0;
}

// What the owner should do next on a project, for the dashboard.
export function nextAction(state: string): { status: string; cta: string; urgent: boolean } {
  switch (state) {
    case "draft": return { status: "Waiting for a script", cta: "Continue", urgent: true };
    case "script_ready": return { status: "Script ready for your review", cta: "Review script", urgent: true };
    case "script_approved":
    case "interviewing": return { status: "Your AI interview is waiting", cta: "Start interview", urgent: true };
    case "awaiting_founder": return { status: "Waiting for your founder to record", cta: "Open", urgent: false };
    case "processing_founder": return { status: "Answers ready to review", cta: "Review and make video", urgent: true };
    case "rendering_anchor":
    case "anchor_ready":
    case "merging": return { status: "We're making your video", cta: "See progress", urgent: false };
    case "failed": return { status: "Something went wrong", cta: "Fix and retry", urgent: true };
    case "limit_reached": return { status: "Paused: a usage limit was reached", cta: "See why", urgent: true };
    default: return { status: stateLabel(state), cta: "Open", urgent: false };
  }
}
