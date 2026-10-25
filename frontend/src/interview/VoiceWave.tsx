// The interviewer has no face: while it talks, a row of bars pulses to its voice; when it listens, they rest as a flat line.
const BARS = 21;

export function VoiceWave({ speaking }: { speaking: boolean }) {
  return (
    <div className="voice-wave" data-speaking={speaking} aria-hidden="true">
      {Array.from({ length: BARS }, (_, i) => (
        <span key={i} style={{ animationDelay: `${((i * 37) % 11) * -90}ms`, animationDuration: `${620 + ((i * 53) % 7) * 70}ms` }} />
      ))}
    </div>
  );
}
