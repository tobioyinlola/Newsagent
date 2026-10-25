import { guest, must } from "../founder/guestApi";

// A still of the person while they answer. The recording is the video; this is kept with the answer as its picture
// (shown beside their words in the final video, and in the review screen).
export function grabFrame(video: HTMLVideoElement, maxWidth = 640): Promise<Blob | null> {
  if (!video.videoWidth || !video.videoHeight) return Promise.resolve(null);
  const scale = Math.min(1, maxWidth / video.videoWidth);
  const c = document.createElement("canvas");
  c.width = Math.round(video.videoWidth * scale);
  c.height = Math.round(video.videoHeight * scale);
  const ctx = c.getContext("2d");
  if (!ctx) return Promise.resolve(null);
  ctx.drawImage(video, 0, 0, c.width, c.height);
  return new Promise((resolve) => c.toBlob((b) => resolve(b), "image/jpeg", 0.85));
}

export async function uploadSnapshot(token: string, takeId: string, blob: Blob): Promise<void> {
  const slot = await must(guest.POST("/v1/interview/{token}/photo", { params: { path: { token } }, body: { content_type: "image/jpeg" } }));
  const put = await fetch(slot.upload_url, { method: "PUT", body: blob });
  if (!put.ok) throw new Error("snapshot upload failed");
  await must(guest.POST("/v1/interview/{token}/photo/confirm", { params: { path: { token } }, body: { key: slot.key, take_id: takeId } }));
}
