/// <reference types="node" />
// The page is light only until tokens.css has dark values: with "light dark", a
// dark system theme puts the browser's dark background behind our dark text.
// Reads the file with fs: under Vitest a CSS import is empty.
// Owner: B

import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";

const css = readFileSync(new URL("../../index.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const tokens = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");

describe("page theme", () => {
  test("light only while the tokens have no dark values", () => {
    expect(tokens).not.toContain("prefers-color-scheme");
    expect(css).toMatch(/color-scheme:\s*light;/);
  });

  test("the page paints its own background and text", () => {
    const body = /body\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(body).toContain("background: var(--color-surface");
    expect(body).toContain("color: var(--color-text");
  });
});
