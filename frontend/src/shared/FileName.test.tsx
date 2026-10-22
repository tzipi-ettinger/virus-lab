// @vitest-environment jsdom
// Owner: B

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { FileName } from "./FileName";
import { shortFileName } from "./shortFileName";

afterEach(cleanup);

describe("shortFileName", () => {
  test("a short name stays whole", () => {
    expect(shortFileName("טופס 3.pdf")).toEqual({ head: "טופס ", tail: "3.pdf", cut: false });
  });

  test("a long name keeps its start and its last word, cut at a space", () => {
    expect(shortFileName("צילום מסך 2026-10-22 145900.png")).toEqual({
      head: "צילום מסך",
      tail: "145900.png",
      cut: true,
    });
  });

  test("one long word keeps its end", () => {
    const { tail, cut } = shortFileName("a".repeat(40) + ".pdf");
    expect(cut).toBe(true);
    expect(tail.endsWith(".pdf")).toBe(true);
    expect(tail.length).toBe(12);
  });
});

describe("FileName", () => {
  test("a cut name has the full name in its tooltip, and the last word left to right", () => {
    render(<FileName name="צילום מסך 2026-10-22 145900.png" />);
    const shown = screen.getByTitle("צילום מסך 2026-10-22 145900.png");
    expect(shown.textContent).toBe("צילום מסך…145900.png");
    expect(shown.querySelector("bdi[dir=ltr]")?.textContent).toBe("145900.png");
  });

  test("a whole name has no tooltip", () => {
    const { container } = render(<FileName name="טופס 3.pdf" />);
    expect(container.querySelector("[title]")).toBeNull();
    expect(container.textContent).toBe("טופס 3.pdf");
  });
});
