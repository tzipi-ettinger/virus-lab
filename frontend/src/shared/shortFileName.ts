// Shortening a long file name in the middle, for FileName.
// Owner: B

export const FILE_NAME_MAX = 24;

/** The name's start and its last word, with "…" between them when it is cut. */
export function shortFileName(name: string, max = FILE_NAME_MAX): { head: string; tail: string; cut: boolean } {
  const space = name.search(/\S+$/);
  const head = space > 0 ? name.slice(0, space) : "";
  const tail = space > 0 ? name.slice(space) : name;
  if (name.length <= max) return { head, tail, cut: false };
  // The last word stays whole unless it alone is too long; then its end stays.
  const keep = Math.ceil(max / 2);
  const end = tail.length > keep ? tail.slice(-keep) : tail;
  let start = name.slice(0, Math.max(max - end.length - 1, 1));
  // Cut at a space when one is near, not in the middle of a word.
  const lastSpace = start.trimEnd().lastIndexOf(" ");
  if (lastSpace >= 4) start = start.slice(0, lastSpace);
  return { head: start.trimEnd(), tail: end, cut: true };
}
