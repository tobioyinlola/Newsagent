// Local visual smoke: fixture clips and tone audio, never customer content or a paid provider.
import { renderOne, renderThumbnail } from "./render";
import type { MergeProps, Scene } from "./compositions/InterviewMerge";

const scenes: Scene[] = [{ type: "anchor", src: "presenter-clip.mp4", seconds: 2 }];
for (let q = 0; q < 4; q++) {
  scenes.push({ type: "question", src: "presenter-clip.mp4", seconds: 1 });
  scenes.push({ question: "What problem is your business solving for customers?", questionNumber: q + 1, totalQuestions: 4, cues: [{ start: 0, end: 2, text: "We help independent businesses connect with customers and grow their operations." }], type: "answer", src: "founder-answer.mp4", seconds: 2, pipSrc: "presenter-clip.mp4", founder: { name: "Ada Obi", title: "CEO, Acme Technology Limited", location: "Lagos, Nigeria" }, headline: ["OBI: Helping farmers connect directly with buyers", "OBI: Bringing appointment tools to independent businesses", "OBI: Building a team around customer needs", "OBI: Planning the next chapter across new cities"][q] });
}
scenes.push({ type: "anchor", src: "presenter-clip.mp4", seconds: 2 }, { type: "anchor", src: "presenter-clip.mp4", seconds: 2 });
const props: MergeProps = { channel: { name: "Cover Founder" }, disclosures: { tag: "Featured", anchor: "AI-generated anchor" }, brand: { primary: "#222222", accent: "#c0fe73" }, tickerLines: ["Cover Founder News • Local broadcast layout preview"], layout: "full", scenes, totalSeconds: 18, headline: "A business story told by the people building it", presenter: { name: "Marcus Richard", title: "Business Reporter, CF News" }, anchorFullFrame: true, anchorCovers: false, liveLocation: "Toronto, Canada", publishedLabel: "OCT 31, 2026 · 10:42 AM EDT" };
if (!process.argv.includes("--stills-only")) await renderOne({ composition: "InterviewMerge", format: "16x9", props, scale: .5, outFile: "/tmp/cf-broadcast-layout-preview.mp4" });
await renderThumbnail("16x9", { ...props, thumbnailAtSeconds: 4 }, "/tmp/cf-broadcast-founder.png", "InterviewMerge");
await renderThumbnail("16x9", { ...props, thumbnailAtSeconds: 1 }, "/tmp/cf-broadcast-presenter.png", "InterviewMerge");
await renderThumbnail("9x16", { ...props, thumbnailAtSeconds: 4 }, "/tmp/cf-broadcast-founder-portrait.png", "InterviewMerge");
await renderThumbnail("16x9", { ...props, layout: "split", thumbnailAtSeconds: 4 }, "/tmp/cf-broadcast-founder-split.png", "InterviewMerge");
await renderThumbnail("16x9", { ...props, layout: "pip", thumbnailAtSeconds: 4 }, "/tmp/cf-broadcast-founder-pip.png", "InterviewMerge");
await renderThumbnail("16x9", { ...props, layout: "column", thumbnailAtSeconds: 4 }, "/tmp/cf-broadcast-founder-column.png", "InterviewMerge");
console.log("Broadcast preview rendered with fixture clips.");
process.exit(0);
