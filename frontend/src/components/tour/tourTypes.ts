// Guided tours: what a tour is, and how far each person has got. The server keeps the progress (per person), so it follows them between devices.
export type TourStep = {
  title: string;
  body: string;
  target?: string; // the data-tour="..." name of the thing to point at; without one the step is a centred card
  route?: string; // go here first (the step is about something on another page)
};
export type TourDef = {
  id: string; // lower-case letters, digits and dashes
  title: string;
  summary: string; // one line on what the tour covers and who it is for
  steps: TourStep[];
  needs?: string[]; // back office: shown only to people holding at least one of these permissions
};
export type TourProgress = { step: number; done: boolean; dismissed: boolean };
export type TourProgressMap = Record<string, Partial<TourProgress> | undefined>;
export type TourBackend = {
  load: () => Promise<TourProgressMap>;
  save: (id: string, patch: { step?: number; done?: boolean; dismissed?: boolean; reset?: boolean }) => Promise<TourProgressMap>;
};

/** How many steps of a tour have been seen, 0 to its length. */
export function stepsSeen(def: TourDef, p: Partial<TourProgress> | undefined): number {
  if (!p) return 0;
  return p.done ? def.steps.length : Math.min(def.steps.length, Math.max(0, p.step ?? 0));
}
