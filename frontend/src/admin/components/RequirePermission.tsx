import type { ReactNode } from "react";
import { useCan } from "../lib/can";
import { Notice } from "./ui";

// A page for people whose role includes at least one of these permissions. Anyone else sees why, not a blank page.
export function RequirePermission({ any, children }: { any: string[]; children: ReactNode }) {
  const can = useCan();
  if (!can(...any)) return <Notice tone="warn">Your role doesn't include this part of the back office. Ask an admin if you need it.</Notice>;
  return <>{children}</>;
}
