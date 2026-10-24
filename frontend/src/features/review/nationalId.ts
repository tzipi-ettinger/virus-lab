// The ID check while typing: the same check digit the server runs
// (rules/validators.py), so a typo shows before saving. The server still decides.
// Owner: B

import { t } from "../../i18n";

/** Ministry of Interior check digit over 9 digits: weights 1,2,1,2..., digit sums. */
export function idChecksumOk(id: string): boolean {
  let total = 0;
  for (let i = 0; i < id.length; i++) {
    const product = Number(id[i]) * (i % 2 === 0 ? 1 : 2);
    total += product > 9 ? product - 9 : product;
  }
  return total % 10 === 0;
}

/**
 * What is wrong with a typed ID, or null. Short IDs are padded with zeros the way
 * the server pads them (5-9 digits). Nothing is said while fewer than 5 are typed.
 */
export function idProblem(text: string): string | null {
  const digits = text.replace(/\D/g, "");
  if (digits.length < 5) return null;
  if (digits.length > 9) return t("review.nationalId.tooLong");
  const id = digits.padStart(9, "0");
  if (!/[1-9]/.test(id) || !idChecksumOk(id)) return t("review.nationalId.checksum");
  return null;
}
