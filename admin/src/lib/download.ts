import { getToken } from "./auth";

// Authenticated file download (the API needs the bearer token, so a plain <a href> would not work).
export async function downloadAuthed(path: string, filename: string) {
  const res = await fetch(`${import.meta.env.VITE_API_URL ?? ""}${path}`, { headers: { Authorization: `Bearer ${getToken() ?? ""}` } });
  if (!res.ok) throw new Error("Download failed. Please try again.");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}
