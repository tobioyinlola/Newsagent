// The interview is designed to fit in 5 minutes. This is the same rule the server documents in services/interview.py
// (answer_window_s): each answer gets the time left, shared across the questions still to ask, minus the time the
// interviewer needs to speak, never more than 75 s and never less than 15 s.
export const MAX_TOTAL_S = 300;
export const MAX_ANSWER_S = 75;
export const MIN_ANSWER_S = 15;
const RESERVE_S = 14; // the closing line
const SPEAKING_S = 9; // the interviewer speaking one question

export function answerWindow(elapsedS: number, questionsLeft: number, max = MAX_ANSWER_S, min = MIN_ANSWER_S): number {
  if (questionsLeft <= 0) return 0;
  const cap = (MAX_TOTAL_S - elapsedS - RESERVE_S) / questionsLeft - SPEAKING_S;
  return Math.floor(Math.max(min, Math.min(max, cap)));
}

export const mmss = (s: number) => {
  const t = Math.max(0, Math.ceil(s));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};
