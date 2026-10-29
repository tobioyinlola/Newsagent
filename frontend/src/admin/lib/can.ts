import { useMe } from "../components/RequireOperator";

// What the signed-in person may do in the back office. The server decides for real on every request; this only hides what
// they can't use. `can("a", "b")` is true when they hold at least one of them.
export function useCan() {
  const me = useMe();
  const held = new Set(me.data?.permissions ?? []);
  return (...wanted: string[]) => wanted.some((p) => held.has(p));
}

// The first screen a person can open: where "/" sends someone whose role has no overview.
export const HOME_ORDER: [string, string[]][] = [
  ["/", ["overview.view"]],
  ["/customers", ["customers.view"]],
  ["/revenue", ["finance.view"]],
  ["/operations", ["operations.view"]],
  ["/review", ["review.manage"]],
  ["/presenter", ["presenter.manage"]],
  ["/audit", ["audit.view"]],
  ["/team", ["team.manage"]],
  ["/security", []],
];
