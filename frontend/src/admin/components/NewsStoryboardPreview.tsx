import { useEffect, useState } from "react";

type Scene = { narration: string; image_hint: string; image_id: string | null; motion: string; duration_s: number };
export function NewsStoryboardPreview({ scenes, images }: { scenes: Scene[]; images: { id: string; url: string }[] }) {
  const [index, setIndex] = useState(0); const [playing, setPlaying] = useState(false);
  const scene = scenes[index % Math.max(1, scenes.length)];
  useEffect(() => {
    if (!playing || !scene) return;
    const timer = window.setTimeout(() => { if (index + 1 >= scenes.length) setPlaying(false); else setIndex(i => i + 1); }, Math.max(3, scene.duration_s) * 1000);
    return () => window.clearTimeout(timer);
  }, [playing, index, scene, scenes.length]);
  if (!scene) return null;
  const image = images.find(i => i.id === scene.image_id);
  return <section aria-label="Image sequence preview" className="mt-5 rounded-xl border border-line bg-ink p-4 text-white"><div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-sm text-white">Storyboard preview</h3><span className="text-xs text-white/70">Scene {index % scenes.length + 1} of {scenes.length} · {scene.duration_s}s</span></div><div className="relative aspect-video overflow-hidden rounded-lg bg-[#343a30]">{image ? <img key={`${index}-${image.id}-${scene.motion}`} src={image.url} alt={scene.image_hint || `Scene ${index + 1}`} className="news-scene-image h-full w-full object-cover" data-motion={scene.motion} style={{ animationDuration: `${scene.duration_s}s`, animationPlayState: playing ? "running" : "paused" }} /> : <div className="flex h-full items-center justify-center p-6 text-center text-sm text-white/70">Assign a story image to this scene to preview its motion.</div>}<div className="absolute bottom-3 left-3 rounded bg-ink px-3 py-1 text-xs font-bold text-brand-green">CF Technology Breaking News</div></div><p className="mt-3 max-h-28 overflow-y-auto text-xs leading-relaxed text-white/80">{scene.narration}</p><div className="mt-3 flex gap-3"><button type="button" className="min-h-10 rounded border border-white/40 px-3 text-xs" disabled={index === 0} onClick={() => { setPlaying(false); setIndex(i => i - 1); }}>Previous scene</button><button type="button" className="min-h-10 rounded border border-brand-green px-3 text-xs font-bold text-brand-green" onClick={() => { if (!playing && index + 1 >= scenes.length) setIndex(0); setPlaying(p => !p); }}>{playing ? "Pause preview" : "Play image preview"}</button><button type="button" className="min-h-10 rounded border border-white/40 px-3 text-xs" disabled={index + 1 >= scenes.length} onClick={() => { setPlaying(false); setIndex(i => i + 1); }}>Next scene</button></div><p className="mt-3 text-[11px] text-white/60">Visual planning preview only. Presenter video and audio are not generated.</p></section>;
}
