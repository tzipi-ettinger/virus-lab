/// <reference types="node" />
// The small review buttons keep a usable size: at least 24px (WCAG 2.5.8), and
// 44px on a touch screen. jsdom has no layout, so this reads the CSS rules.
// Owner: B

import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";

const css = readFileSync(new URL("./ReviewTable.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
const SMALL = [".review-confirm", ".review-delete", ".review-list-edit", ".review-list-item button", ".review-approve button"];

/** The smallest min-block-size given to the selector by a rule in this text. */
function minHeight(text: string, selector: string): number {
  const sizes = Array.from(text.matchAll(/([^{}]+)\{([^}]*)\}/g))
    .filter(([, selectors]) => selectors.split(",").some((s) => s.trim() === selector))
    .flatMap(([, , body]) => Array.from(body.matchAll(/min-block-size:\s*(\d+)px/g), (m) => Number(m[1])));
  return sizes.length ? Math.min(...sizes) : 0;
}

describe("review touch targets", () => {
  const media = css.indexOf("@media (pointer: coarse)");
  const base = css.slice(0, media);
  // The rules inside the touch block, without its "@media … {" line.
  const coarse = css.slice(css.indexOf("{", media) + 1);

  test.each(SMALL)("%s is at least 24px, and 44px on touch", (selector) => {
    expect(minHeight(base, selector)).toBeGreaterThanOrEqual(24);
    expect(minHeight(coarse, selector)).toBeGreaterThanOrEqual(44);
  });
});
