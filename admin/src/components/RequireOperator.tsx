import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet } from "react-router-dom";
import { ApiError, api, unwrap } from "../api/client";
import { getToken, signOut } from "../lib/auth";
import { Button, Notice } from "./ui";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/v1/me")), retry: false });
}

// Everything in the back office needs a signed-in operator. A customer who signs in here sees nothing.
export function RequireOperator() {
  const me = useMe();
  if (!getToken()) return <Navigate to="/login" replace />;
  if (me.isLoading) return <p className="p-6" aria-busy="true">Loading…</p>;
  if (me.error instanceof ApiError && me.error.status === 401 && (me.error.detail as { error?: string } | undefined)?.error === "otp_required") return <Navigate to="/otp" replace />;
  if (me.error instanceof ApiError && me.error.status === 401) return <Navigate to="/login?expired=1" replace />;
  if (me.error || !me.data) return <div className="mx-auto max-w-md p-6"><Notice tone="warn">We couldn't load your account. Please try again.</Notice></div>;
  if (!me.data.is_operator)
    return (
      <div className="mx-auto max-w-md space-y-3 p-6">
        <Notice tone="warn">This account isn't a Cover Founder operator, so it can't use the back office. Customers sign in at the main app.</Notice>
        <Button onClick={() => { signOut(); location.assign("/login"); }}>Sign out</Button>
      </div>
    );
  return <Outlet />;
}
