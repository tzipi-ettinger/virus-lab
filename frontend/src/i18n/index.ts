// The texts the user sees, by key, from one JSON file per language (he.json for now),
// like the server's app/i18n. Code holds only keys: the wording changes in one place,
// and another language is another file with the same keys. A key that is not in the
// file does not compile. No React here; a sentence with an element in it is rich.ts.
// Owner: B

import he from "./he.json";

/** "records.counts.pending" for every text in the file, as a type. */
type Keys<T, Prefix extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${Prefix}${K}` : Keys<T[K], `${Prefix}${K}.`>;
}[keyof T & string];

export type TextKey = Keys<typeof he>;

/** The text under a key, each {name} in it replaced from values. A {name} with no value stays. */
export function t(key: TextKey, values: Record<string, string | number> = {}): string {
  const text = key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], he);
  if (typeof text !== "string") throw new Error(`no text for "${key}"`);
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in values ? String(values[name]) : whole));
}
