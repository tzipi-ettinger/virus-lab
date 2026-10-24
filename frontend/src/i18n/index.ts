// The texts the user sees, by key, from one JSON file per language: he.json and
// en.json, with the same keys (sources.test.ts checks it). Like the server's app/i18n,
// code holds only keys, and a key that is not in the files does not compile.
// The language is picked once, when the page loads: texts made at import time (the
// table's columns, the status names) then come out in it too. Switching saves the
// choice and loads the page again. No React here; a sentence with an element in it
// is rich.ts.
// Owner: B

import en from "./en.json";
import he from "./he.json";

/** "records.counts.pending" for every text in the file, as a type. */
type Keys<T, Prefix extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${Prefix}${K}` : Keys<T[K], `${Prefix}${K}.`>;
}[keyof T & string];

export type TextKey = Keys<typeof he>;

// Typed as he.json, so a key missing from en.json does not compile either.
const TEXTS: Record<Language, typeof he> = { he, en };

export const LANGUAGES = {
  he: { dir: "rtl", locale: "he-IL" },
  en: { dir: "ltr", locale: "en-GB" },
} as const;

export type Language = keyof typeof LANGUAGES;

export const LANGUAGE_KEY = "language";

/** The saved choice, else Hebrew. Storage may be blocked (a private window): Hebrew. */
function savedLanguage(): Language {
  try {
    return globalThis.localStorage?.getItem(LANGUAGE_KEY) === "en" ? "en" : "he";
  } catch {
    return "he";
  }
}

export const language: Language = savedLanguage();

/** The language's locale, for numbers (Intl). */
export const locale = LANGUAGES[language].locale;

/** The text under a key, each {name} in it replaced from values. A {name} with no value stays. */
export function t(key: TextKey, values: Record<string, string | number> = {}): string {
  const text = key
    .split(".")
    .reduce<unknown>((node, part) => (node as Record<string, unknown>)?.[part], TEXTS[language]);
  if (typeof text !== "string") throw new Error(`no text for "${key}"`);
  return text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in values ? String(values[name]) : whole));
}

/** The page in the language: its lang, its direction and its title. */
export function applyLanguage(root: HTMLElement = document.documentElement) {
  root.lang = language;
  root.dir = LANGUAGES[language].dir;
  document.title = t("app.title");
}

/** Saves the choice and loads the page again in it. */
export function chooseLanguage(next: Language, reload: () => void = () => window.location.reload()) {
  try {
    localStorage.setItem(LANGUAGE_KEY, next);
  } catch {
    return; // nowhere to keep it: stay as we are
  }
  reload();
}
