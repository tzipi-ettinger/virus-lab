// The e2e user and signing in, shared by the specs.
// Owner: shared

import type { Page } from "@playwright/test";

export const USER = process.env.E2E_USER ?? "e2e";
export const PASSWORD = process.env.E2E_PASSWORD ?? "";

export function requirePassword() {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD to the password of E2E_USER (default: e2e)");
}

export async function signIn(page: Page) {
  await page.getByLabel("שם משתמש").fill(USER);
  await page.getByLabel("סיסמה", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: /^כניסה/ }).click();
}
