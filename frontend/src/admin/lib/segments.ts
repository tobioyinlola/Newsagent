// Types and wording for marketing segments. The server owns the list of fields; this only turns rules into sentences.
export type FieldDef = { key: string; label: string; group: string; kind: "number" | "bool" | "choice" | "dates"; ops: string[]; unit: string; options: { value: string; label: string }[] };
export type Condition = { field: string; op: string; value: unknown };
export type Rules = { match: "all" | "any"; conditions: Condition[] };
export type Preview = { matched: number; reachable: number; excluded: number; sample: { user_id: string; email: string; company: string; joined: string }[] };
export type Segment = { id: string; name: string; description: string; rules: Rules; created_by: string; created_at: string; preview?: Preview };

export const OP_LABEL: Record<string, string> = { gte: "at least", lte: "at most", eq: "exactly", between: "between", is: "is", in: "is one of" };

// A fresh rule with a sensible starting value for its kind.
export function blankCondition(f: FieldDef): Condition {
  const op = f.ops[0];
  const value = f.kind === "bool" ? true : f.kind === "choice" ? [] : f.kind === "dates" || op === "between" ? ["", ""] : "";
  return { field: f.key, op, value };
}

// Numbers typed into boxes are strings; send real numbers so saved rules stay clean.
export function cleanRules(r: Rules): Rules {
  const n = (v: unknown) => (typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v)) ? Number(v) : v);
  return { match: r.match, conditions: r.conditions.map((c) => ({ ...c, value: Array.isArray(c.value) && c.op === "between" && !String(c.field).includes("dates") ? c.value.map(n) : c.field === "joined_dates" ? c.value : c.op === "in" || c.op === "is" ? c.value : n(c.value) })) };
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
