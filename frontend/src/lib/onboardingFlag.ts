// Whether new customers are taken through the first-run questions and tours open by themselves. On everywhere except the automated
// browser tests' main server, so that the many tests that sign people up and click around are not interrupted. The Guided tours menu works either way.
export const ONBOARDING_ON = import.meta.env.VITE_ONBOARDING !== "off";
