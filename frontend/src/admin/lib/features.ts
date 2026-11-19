// Parts of the back office that can be hidden. Outreach is shown unless the web app is built with VITE_SHOW_OUTREACH set to "false".
export const SHOW_OUTREACH = import.meta.env.VITE_SHOW_OUTREACH !== "false";
