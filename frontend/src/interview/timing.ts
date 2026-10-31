// Every answer has 60 seconds, preceded by a five-second countdown and followed by five seconds to round up.
export const MAX_TOTAL_S = 360; // estimate for the programme, never used to shorten an answer
export const MAX_ANSWER_S = 60;
export const MIN_ANSWER_S = 15;
export const COUNTDOWN_S = 5;
export const ROUND_UP_S = 5;

export function answerWindow(_elapsedS: number, questionsLeft: number, max = MAX_ANSWER_S, _min = MIN_ANSWER_S): number {
  void _elapsedS; void _min;
  return questionsLeft > 0 ? Math.floor(max) : 0;
}

export function answerTiming(elapsed: number, answerSeconds = MAX_ANSWER_S) {
  const roundingUp = elapsed >= answerSeconds;
  return { roundingUp, remaining: Math.max(0, (roundingUp ? answerSeconds + ROUND_UP_S : answerSeconds) - elapsed), shouldStop: elapsed >= answerSeconds + ROUND_UP_S };
}

export const mmss = (s: number) => {
  const t = Math.max(0, Math.ceil(s));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};
