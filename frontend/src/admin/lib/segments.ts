// Types and wording for marketing segments. The server owns the list of fields; this only turns rules into sentences.
export type FieldDef = { key: string; label: string; group: string; kind: "number" | "bool" | "choice" | "dates"; ops: string[]; unit: string; options: { value: string; label: string }[] };
export type Condition = { field: string; op: string; value: unknown };
export type Rules = { match: "all" | "any"; conditions: (Condition | Rules)[] };
export const isGroup = (x: Condition | Rules): x is Rules => "conditions" in x;
export const MAX_DEPTH = 3; // a group inside a group inside a group
export type Preview = { matched: number; reachable: number; excluded: number; sample: { user_id: string; email: string; company: string; joined: string }[] };
export type Segment = { id: string; name: string; description: string; rules: Rules; created_by: string; created_at: string; preview?: Preview };

export const OP_LABEL: Record<string, string> = { gte: "at least", lte: "at most", eq: "exactly", between: "between", is: "is", in: "is one of" };

// A fresh rule with a sensible starting value for its kind.
export function blankCondition(f: FieldDef): Condition {
  const op = f.ops[0];
  const value = f.kind === "bool" ? true : f.kind === "choice" ? [] : f.kind === "dates" || op === "between" ? ["", ""] : "";
  return { field: f.key, op, value };
}

// Numbers typed into boxes are strings; send real numbers so saved rules stay clean. Groups are cleaned the same way inside.
const num = (v: unknown) => (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v)) ? Number(v) : v);
function cleanCondition(c: Condition): Condition {
  const value = Array.isArray(c.value) && c.op === "between" && !String(c.field).includes("dates") ? c.value.map(num) : c.field === "joined_dates" ? c.value : c.op === "in" || c.op === "is" ? c.value : num(c.value);
  return { ...c, value };
}
export function cleanRules(r: Rules): Rules {
  return { match: r.match, conditions: r.conditions.map((c) => (isGroup(c) ? cleanRules(c) : cleanCondition(c))) };
}

// How many single rules there are, groups included.
export const countRules = (r: Rules): number => r.conditions.reduce((n, c) => n + (isGroup(c) ? countRules(c) : 1), 0);

// A whole rule set as one sentence: groups go in brackets.
export function describeRules(r: Rules, fields: FieldDef[]): string {
  return r.conditions.map((c) => (isGroup(c) ? `(${describeRules(c, fields)})` : describe(c, fields))).join(r.match === "all" ? " AND " : " OR ");
}

export function describe(c: Condition, fields: FieldDef[]): string {
  const f = fields.find((x) => x.key === c.field);
  if (!f) return c.field;
  const unit = f.unit ? ` ${f.unit}` : "";
  if (f.kind === "bool") return `${f.label}: ${c.value ? "yes" : "no"}`;
  if (f.kind === "choice") return `${f.label} is ${((c.value as string[]) ?? []).map((v) => f.options.find((o) => o.value === v)?.label ?? v).join(" or ") || "…"}`;
  if (f.kind === "dates" || c.op === "between") { const [a, b] = (c.value as unknown[]) ?? []; return `${f.label} ${f.kind === "dates" ? "" : "between "}${a || "…"} and ${b || "…"}${unit}`.replace("  ", " "); }
  return `${f.label} ${OP_LABEL[c.op] ?? c.op} ${String(c.value || "…")}${unit}`;
}
