// Owner: B

import { describe, expect, test } from "vitest";
import { idChecksumOk, idProblem } from "./nationalId";

describe("idChecksumOk", () => {
  test("a valid ID passes and one changed digit fails", () => {
    expect(idChecksumOk("011223344")).toBe(true);
    expect(idChecksumOk("011223345")).toBe(false);
  });
});

describe("idProblem", () => {
  test("nothing is said while typing the first digits", () => {
    expect(idProblem("")).toBeNull();
    expect(idProblem("0112")).toBeNull();
  });

  test("a valid ID, with or without its leading zero, is fine", () => {
    expect(idProblem("011223344")).toBeNull();
    expect(idProblem("11223344")).toBeNull();
    expect(idProblem("011-22-3344")).toBeNull();
  });

  test("a wrong check digit is named", () => {
    expect(idProblem("011223345")).toContain("ספרת הביקורת");
  });

  test("too many digits, and all zeros, are named", () => {
    expect(idProblem("0112233440")).toContain("9 ספרות");
    expect(idProblem("000000000")).toContain("ספרת הביקורת");
  });
});
