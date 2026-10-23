// The AI interviewer speaking. Prefers the server's audio (a real voice) and falls back to the browser's own speech
// synthesis. Whatever happens, the returned promise settles in bounded time, so a missing voice can never freeze the
// interview: the line is also shown as captions.
export type VoiceLine = { key: string; text: string; audio_url?: string | null };

const FAST = import.meta.env.VITE_INTERVIEW_FAST === "1"; // test builds only: skips the waiting, never set in production
const wordsOf = (t: string) => t.trim().split(/\s+/).filter(Boolean).length;

export type Speaking = { cancel: () => void; done: Promise<void> };

export function speak(line: VoiceLine, onStart?: () => void): Speaking {
  let cancelled = false;
  let stop: () => void = () => undefined;
  const done = new Promise<void>((resolve) => {
    let finished = false;
    const finish = () => { if (!finished) { finished = true; clearTimeout(guard); stop(); resolve(); } };
    const words = wordsOf(line.text);
    // the longest we will wait for any voice: reading speed plus slack
    const guard = setTimeout(finish, FAST ? 150 : Math.max(2500, words * 600 + 3000));
    stop = () => undefined;
    if (FAST) { onStart?.(); return; }

    const viaBrowser = () => {
      const synth = typeof window !== "undefined" ? window.speechSynthesis : undefined;
      if (!synth || typeof SpeechSynthesisUtterance === "undefined") {
        onStart?.();
        setTimeout(finish, Math.max(1500, words * 380)); // no voice at all: pace it like reading, captions carry it
        return;
      }
      const u = new SpeechSynthesisUtterance(line.text);
      u.lang = "en-GB"; u.rate = 1;
      u.onstart = () => onStart?.();
      u.onend = finish; u.onerror = finish;
      stop = () => synth.cancel();
      onStart?.();
      synth.speak(u);
    };

    if (line.audio_url) {
      const a = new Audio(line.audio_url);
      stop = () => { a.pause(); };
      a.onplaying = () => onStart?.();
      a.onended = finish;
      a.onerror = () => { if (!cancelled) viaBrowser(); };
      a.play().catch(() => { if (!cancelled) viaBrowser(); });
    } else {
      viaBrowser();
    }
  });
  return { cancel: () => { cancelled = true; stop(); }, done };
}
