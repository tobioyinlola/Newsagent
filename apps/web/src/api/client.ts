import createClient from "openapi-fetch";
import type { paths } from "./schema";

// Dev-only bearer; real auth (Clerk/Auth0) replaces this in Phase 1.
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_URL ?? "",
  headers: { Authorization: `Bearer ${localStorage.getItem("token") ?? ""}` },
});
