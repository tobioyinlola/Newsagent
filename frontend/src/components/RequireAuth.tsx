import { Navigate, Outlet } from "react-router-dom";
import { ApiError } from "../api/client";
import { getToken } from "../lib/auth";
import { Notice } from "./ui";
import { useMe } from "./Layout";

export function RequireAuth() {
  const me = useMe();
  if (!getToken()) return <Navigate to="/login" replace />;
  if (me.isLoading) return <p className="p-6" aria-busy="true">Loading…</p>;
  if (me.error instanceof ApiError && me.error.status === 401 && (me.error.detail as { error?: string } | undefined)?.error === "otp_required")
    return <Navigate to="/otp" replace />;
  if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/login?expired=1" replace />;
  if (me.error instanceof ApiError && me.error.status === 403)
    return <div className="mx-auto max-w-md p-6"><Notice tone="warn">This email has no account yet. Sign-up is invite-only: open your invite link, or ask for one.</Notice></div>;
  return <Outlet />;
}
