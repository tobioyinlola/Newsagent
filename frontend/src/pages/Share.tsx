import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { DisclosureBadge } from "../components/ui";

// Public page: no sign-in. The disclosure is part of the page and cannot be turned off.
export function Share() {
  const { token = "" } = useParams();
  const q = useQuery({ queryKey: ["share", token], queryFn: () => unwrap(api.GET("/v1/share/{token}", { params: { path: { token } } })), retry: false });
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      {q.isLoading && <p aria-busy="true">Loading…</p>}
      {q.error && <p role="alert" className="rounded-md border border-ink bg-white p-6 text-center">This link is no longer available.</p>}
      {q.data && (
        <>
          <h1 className="text-2xl font-bold">{q.data.title}</h1>
          <video controls className="w-full rounded-md bg-black" src={q.data.video_url} poster={q.data.thumbnail_url ?? undefined} aria-label={`Video: ${q.data.title}`} />
          <DisclosureBadge text={q.data.disclosure} />
        </>
      )}
    </div>
  );
}
