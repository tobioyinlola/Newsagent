// How an announcement looks to a customer. The same card is the pop-up after sign-in and the preview in the back office.
export type AnnouncementView = { title: string; message: string; button_label?: string; button_url?: string };

export function AnnouncementCard({ a, children }: { a: AnnouncementView; children?: React.ReactNode }) {
  return (
    <div className="w-full overflow-hidden rounded-t-2xl border-2 border-ink bg-white text-ink shadow-xl sm:max-w-md sm:rounded-2xl">
      <div className="bg-ink px-5 py-3 text-xs font-bold uppercase tracking-widest text-brand-green">News from Cover Founder</div>
      <div className="space-y-3 p-5">
        <h2 className="text-xl font-bold leading-snug [overflow-wrap:anywhere]">{a.title}</h2>
        <p className="whitespace-pre-wrap text-sm leading-relaxed [overflow-wrap:anywhere]">{a.message}</p>
        {children}
      </div>
    </div>
  );
}
