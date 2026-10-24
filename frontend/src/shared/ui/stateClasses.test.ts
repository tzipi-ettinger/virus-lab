/// <reference types="node" />
// All CSS files load into one page, so a rule for a bare state class such as
// `.is-review { ... }` reaches every screen with that class. The stats card's
// `.is-review` painted the whole review screen yellow. A state class must sit
// on a component class: `.stats-status .is-review`, `.upload-kind.is-pdf`.
// Reads the files with fs: under Vitest a CSS import, even with ?raw, is empty.
// Owner: shared

import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, test } from "vitest";

const SRC = new URL("../../", import.meta.url);

// Without /* comments */: a selector in one is not a rule.
const read = (path: string) =>
  readFileSync(new URL(path, SRC), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

const sheets = new Map(
  readdirSync(SRC, { recursive: true, encoding: "utf8" })
    .map((path) => path.replaceAll("\\", "/"))
    .filter((path) => path.endsWith(".css"))
    .map((path) => [path, read(path)]),
);

// A selector that is only `.is-something`, at the start of a rule or after a comma.
const BARE_STATE = /(?:^|[{},])\s*(\.is-[\w-]+)\s*[{,]/gm;

describe("state classes", () => {
  test("no CSS rule targets a state class on its own", () => {
    const bare = [...sheets].flatMap(([path, text]) =>
      Array.from(text.matchAll(BARE_STATE), (m) => `${m[1]} in ${path}`),
    );
    expect(bare).toEqual([]);
  });

  test("catches a bare state class", () => {
    // Guards the test above: a pattern that never matches would pass without checking anything.
    expect(".is-review {\n  color: red;\n}".match(BARE_STATE)).not.toBeNull();
    expect(".stats-status .is-review {\n  color: red;\n}".match(BARE_STATE)).toBeNull();
    expect(sheets.get("features/stats/StatsPage.css")).toContain(".is-review");
  });
});
