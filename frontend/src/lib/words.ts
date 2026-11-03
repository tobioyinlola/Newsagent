/** How many words a text has: runs of non-space characters, so line breaks and extra spaces never count. */
export const countWords = (text: string): number => (text.trim() ? text.trim().split(/\s+/).length : 0);

/** The text cut to at most `max` words. Typing or pasting past the limit drops the extra words; spacing and line breaks inside
 *  the kept words are untouched, and text already within the limit is returned exactly as it is. */
export function limitWords(text: string, max: number): string {
  let seen = 0;
  for (const m of text.matchAll(/\S+/g)) {
    seen += 1;
    if (seen > max) return text.slice(0, (m.index ?? 0)).trimEnd();
  }
  return text;
}
