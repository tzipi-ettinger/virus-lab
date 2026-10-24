/// <reference types="node" />
// Two guards over the sources: no text the user sees is written in the code (it
// belongs in he.json), and no text in he.json is left that nothing uses.
// Reads the files with fs, like tokens.test.ts.
// Owner: B

import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, test } from "vitest";
import he from "./he.json";

const SRC = new URL("../", import.meta.url);
const HEBREW = /[֐-׿]/;

// Without comments: Hebrew in a comment, or a key named in one, is not code.
const stripComments = (text: string) =>
  text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");

const sources = new Map(
  readdirSync(SRC, { recursive: true, encoding: "utf8" })
    .map((path) => path.replaceAll("\\", "/"))
    .filter((path) => /\.(ts|tsx)$/.test(path) && !/\.test\.tsx?$/.test(path) && !path.endsWith("schema.d.ts"))
    .map((path) => [path, stripComments(readFileSync(new URL(path, SRC), "utf8"))]),
);

// Sample records for the tests: names and senders as data, not texts the user sees.
const TEST_DATA = new Set(["features/review/testRecords.ts"]);

function leaves(node: object, prefix = ""): string[] {
  return Object.entries(node).flatMap(([key, value]) =>
    typeof value === "string" ? [`${prefix}${key}`] : leaves(value as object, `${prefix}${key}.`),
  );
}

describe("the sources", () => {
  test("no text the user sees is written in the code: it is in he.json", () => {
    const written = [...sources]
      .filter(([path]) => !TEST_DATA.has(path))
      .flatMap(([path, text]) =>
        text
          .split("\n")
          .map((line, i) => ({ line, at: `${path}:${i + 1}` }))
          .filter(({ line }) => HEBREW.test(line))
          .map(({ at, line }) => `${at}  ${line.trim()}`),
      );
    expect(written).toEqual([]);
  });

  test("every text in he.json is used, by its key or by a key built from its group", () => {
    const code = [...sources.values()].join("\n");
    const unused = leaves(he).filter((key) => {
      const group = key.slice(0, key.lastIndexOf("."));
      return !code.includes(`"${key}"`) && !code.includes(`\`${group}.\${`);
    });
    expect(unused).toEqual([]);
  });

  test("reads the files it checks", () => {
    // Guards the tests above: with nothing read, they would pass without checking anything.
    expect(sources.get("features/records/RecordsPage.tsx")).toContain('t("records.title")');
    expect(HEBREW.test(sources.get("features/review/testRecords.ts") ?? "")).toBe(true);
    expect(leaves(he).length).toBeGreaterThan(200);
  });
});
