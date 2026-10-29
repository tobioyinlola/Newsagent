// The press release as it is shown: in the app (light, with the media contact, for the owner) and on the public Latest Stories
// pages (dark, without the contact). Pictures the owner uploaded sit between the paragraphs.
export type Contact = { name?: string; title?: string; company?: string; email?: string; website?: string };
export type Story = {
  headline: string;
  dek: string;
  sections: { heading: string; paragraphs: string[] }[];
  social: { hook: string; post: string; hashtags: string[] };
  unverified?: string[];
  dateline?: string | null;
  about?: string;
  company?: string;
  contact?: Contact;
};
export type Picture = { url: string; caption: string };

export const paragraphsOf = (s: Pick<Story, "sections">) => s.sections.flatMap((x) => x.paragraphs);
export const contactLines = (c?: Contact) => [c?.name, c?.title, c?.company, c?.email, c?.website].filter((x): x is string => !!x && x.trim().length > 0);

// Pictures spread through the text: with N pictures and P paragraphs, picture i follows paragraph floor((i + 1) * P / (N + 1)).
export function placePictures<T>(paragraphs: string[], pictures: T[]): { after: number; picture: T }[] {
  const p = paragraphs.length;
  return pictures.map((picture, i) => ({ after: Math.max(1, Math.floor(((i + 1) * p) / (pictures.length + 1))), picture }));
}

export const articleText = (s: Story) =>
  ["FOR IMMEDIATE RELEASE", "", s.headline, s.dek, "", ...paragraphsOf(s).map((p, i) => (i === 0 && s.dateline ? `${s.dateline} — ${p}` : p)).flatMap((p) => [p, ""]), ...(s.about ? [`About ${s.company ?? ""}`.trim(), s.about, ""] : []), ...(contactLines(s.contact).length ? ["Media Contact", ...contactLines(s.contact)] : [])].join("\n").trim();

const TONES = {
  light: { label: "text-muted", dek: "text-muted", body: "text-sm", caption: "text-muted", frame: "border-line", head: "" },
  dark: { label: "text-white/60", dek: "text-white/70", body: "text-base leading-relaxed text-white/90", caption: "text-white/60", frame: "border-white/15", head: "text-white" },
} as const;

export function PressRelease({ story: s, pictures = [], showContact = false, tone = "light", headingLevel = 3 }: { story: Story; pictures?: Picture[]; showContact?: boolean; tone?: keyof typeof TONES; headingLevel?: 2 | 3 }) {
  const t = TONES[tone];
  const paras = paragraphsOf(s);
  const at = placePictures(paras, pictures.filter((x) => x.url));
  const H = (headingLevel === 2 ? "h2" : "h3") as "h2" | "h3";
  return (
    <article className="space-y-3">
      <p className={`text-xs font-bold uppercase tracking-widest ${t.label}`}>For immediate release</p>
      <H className={`text-xl font-bold italic ${t.head}`}>{s.headline}</H>
      <p className={`font-semibold italic ${t.dek}`}>{s.dek}</p>
      {paras.map((p, i) => (
        <div key={i} className="space-y-3">
          <p className={t.body}>{i === 0 && s.dateline ? <><strong className="italic">{s.dateline}</strong> — {p}</> : p}</p>
          {at.filter((x) => x.after === i + 1).map((x) => (
            <figure key={x.picture.url} className="my-1">
              <img src={x.picture.url} alt={x.picture.caption || "Picture for the story"} className={`max-h-80 w-full rounded-sm border object-cover ${t.frame}`} loading="lazy" />
              {x.picture.caption && <figcaption className={`mt-1 text-xs italic ${t.caption}`}>{x.picture.caption}</figcaption>}
            </figure>
          ))}
        </div>
      ))}
      {s.about && (
        <section className="space-y-1">
          <h4 className={`font-bold italic ${t.head}`}>About {s.company}</h4>
          <p className={t.body}>{s.about}</p>
        </section>
      )}
      {showContact && contactLines(s.contact).length > 0 && (
        <section className={`space-y-0.5 text-sm ${t.head}`}>
          <h4 className="font-bold">Media Contact</h4>
          {contactLines(s.contact).map((l, i) => <p key={i}>{l}</p>)}
        </section>
      )}
    </article>
  );
}
