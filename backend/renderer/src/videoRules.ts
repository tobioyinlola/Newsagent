// The Video Rulebook's values, generated from backend/app/video_rules/rulebook.py (never edit the JSON by hand).
import data from "./videoRules.generated.json";

const rules = data.rules as Record<string, unknown>;

/** A rule's value by id, e.g. rule<number>("BIV-GFX-006"). Throws if the id is unknown, so a typo can't silently pass. */
export function rule<T>(id: string): T {
  if (!(id in rules)) throw new Error(`unknown video rule ${id}`);
  return rules[id] as T;
}

export const RULES_VERSION: number = data.version;
