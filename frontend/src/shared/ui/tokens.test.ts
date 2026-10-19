/// <reference types="node" />
// Every token a component uses is defined in tokens.css. Each var() carries a
// fallback, so a misspelled or missing token would never show on screen (#32).
// Reads the files with fs: under Vitest a CSS import, even with ?raw, is empty.
// Owner: shared

import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, test } from "vitest";

const SRC = new URL("../../", import.meta.url);

// Without /* comments */: a var() in one is not a use.
const read = (path: string) =>
  readFileSync(new URL(path, SRC), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

const sources = new Map(
  readdirSync(SRC, { recursive: true, encoding: "utf8" })
    .map((path) => path.replaceAll("\\", "/"))
    .filter((path) => /\.(css|tsx)$/.test(path))
    .map((path) => [path, read(path)]),
);

const defined = new Set(
  Array.from(read("shared/ui/tokens.css").matchAll(/(--[a-z0-9-]+)\s*:/g), (m) => m[1]),
);

describe("tokens.css", () => {
  test("defines every token used under src/", () => {
    const missing = [...sources].flatMap(([path, text]) =>
      Array.from(text.matchAll(/var\(\s*(--[a-z0-9-]+)/g), (m) => m[1])
        .filter((name) => !defined.has(name))
        .map((name) => `${name} in ${path}`),
    );
    expect(missing).toEqual([]);
  });

  test("reads the files it checks", () => {
    // Guards the test above: with nothing read, it would pass without checking anything.
    expect(defined.size).toBeGreaterThan(0);
    expect(sources.get("features/upload/UploadPanel.css")).toContain("var(--color-");
  });
});
