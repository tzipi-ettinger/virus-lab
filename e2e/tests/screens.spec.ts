// Every screen opens, from the menu and by its address, an unknown address shows the
// 404, and each screen holds up: one title, a name on every control, no sideways
// scroll at phone width, and no error in the page (helpers.ts).
// Owner: shared

import { RUN, expect, requirePassword, signIn, signedInRequest, test, uploadViaApi, type ApiRecord } from "./helpers";

let record: ApiRecord;

test.beforeAll(async () => {
  requirePassword();
  const request = await signedInRequest();
  // Two pages: one of the fixtures is a failed read, so a single page may give no record.
  const records = await uploadViaApi(request, `e2e-screens-${RUN}.pdf`, 2);
  expect(records.length).toBeGreaterThan(0);
  record = records[0];
  await request.dispose();
});

/** The screens a signed-in user opens, by address, with the title each opens with.
 *  The upload's title is an h2 under the steps, so it has no h1. */
const SCREENS = () => [
  { path: "/", title: /מטופס סרוק/, h1: 1 },
  { path: "/upload", title: /העלאת טפסי התחייבות/, h1: 0 },
  { path: "/records", title: /^רשומות$/, h1: 1 },
  { path: `/records/${record.record_id}`, title: null, h1: 1 }, // the record's name
  { path: "/stats", title: /^תמונת מצב$/, h1: 1 },
  { path: "/no-such-page", title: /^הדף לא נמצא\.$/, h1: 1 },
];

test("the landing page leads to the upload and to the records", async ({ page }) => {
  await signIn(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("מטופס סרוק");
  await expect(page.getByRole("list").filter({ hasText: "מעלים טפסים" })).toContainText("בודקים ומאשרים");

  await page.getByRole("link", { name: /התחלה: העלאת טפסים/ }).click();
  await expect(page).toHaveURL(/\/upload$/);
  await page.goto("/");
  await page.getByRole("link", { name: "לכל הרשומות" }).click();
  await expect(page).toHaveURL(/\/records$/);
});

test("the menu opens each screen, marks where you are, and shows who is signed in", async ({ page }) => {
  await signIn(page);
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const nav = page.getByRole("navigation", { name: "ניווט ראשי" });
  await expect(page.locator(".layout-user")).toContainText(me.display_name);

  for (const [name, path, heading] of [
    ["רשומות", /\/records$/, "רשומות"],
    ["תמונת מצב", /\/stats$/, "תמונת מצב"],
    ["העלאה ובדיקה", /\/upload$/, "העלאת טפסי התחייבות"],
  ] as const) {
    await nav.getByRole("link", { name }).click();
    await expect(page).toHaveURL(path);
    await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
    await expect(nav.getByRole("link", { name })).toHaveAttribute("aria-current", "page");
  }

  // The logo goes home.
  await page.getByRole("link", { name: "דף הבית" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("an unknown address shows the 404, with the way back", async ({ page }) => {
  await signIn(page);
  await page.goto("/no-such-page");
  await expect(page.getByRole("heading", { level: 1, name: "הדף לא נמצא." })).toBeVisible();
  await page.getByRole("link", { name: "חזרה להעלאה ובדיקה" }).click();
  await expect(page).toHaveURL(/\/upload$/);

  // An unknown API address is a JSON 404, not the app's page.
  const answer = await page.request.get("/api/nope");
  expect(answer.status()).toBe(404);
});

test("every screen has its title, a name on every control, alt text on every image, and unique ids", async ({ page }) => {
  await signIn(page);
  for (const screen of SCREENS()) {
    await page.goto(screen.path);
    if (screen.title) await expect(page.getByRole("heading", { name: screen.title }).first()).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 }), `${screen.path}: h1`).toHaveCount(screen.h1);
    // Wait for the data to land, so the controls checked are the real ones.
    await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
    await expect(page.locator(".skeleton")).toHaveCount(0);

    const problems = await page.evaluate(() => {
      const found: string[] = [];
      const named = (el: Element) =>
        (el.getAttribute("aria-label") ?? "").trim() !== "" ||
        (el.getAttribute("aria-labelledby") ?? "") !== "" ||
        (el.textContent ?? "").trim() !== "" ||
        (el.getAttribute("title") ?? "").trim() !== "";
      for (const el of document.querySelectorAll("button, a[href]")) {
        if (!named(el)) found.push(`no name: ${el.outerHTML.slice(0, 80)}`);
      }
      for (const el of document.querySelectorAll("input:not([type=hidden]):not([aria-hidden=true]), select")) {
        const id = el.id;
        const labelled =
          el.closest("label") !== null ||
          (id && document.querySelector(`label[for="${id}"]`) !== null) ||
          el.hasAttribute("aria-label");
        if (!labelled) found.push(`no label: ${el.outerHTML.slice(0, 80)}`);
      }
      for (const img of document.querySelectorAll("img")) {
        if (!img.hasAttribute("alt")) found.push(`no alt: ${img.outerHTML.slice(0, 80)}`);
      }
      const ids = [...document.querySelectorAll("[id]")].map((el) => el.id);
      for (const id of new Set(ids.filter((id, i) => ids.indexOf(id) !== i))) found.push(`duplicate id: ${id}`);
      return found;
    });
    expect(problems, screen.path).toEqual([]);
  }
});

test("at phone width, no screen scrolls sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  const wider = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(await wider(), "/login").toBeLessThanOrEqual(1);

  await signIn(page);
  for (const screen of SCREENS()) {
    await page.goto(screen.path);
    await expect(page.locator(".skeleton")).toHaveCount(0);
    expect(await wider(), screen.path).toBeLessThanOrEqual(1);
  }
});

test("a change sent from another site is refused, and nothing is served without signing in", async ({ page }) => {
  await signIn(page);
  // The session cookie goes along, but the Origin is not ours (CSRF).
  const elsewhere = await page.request.post(`/api/v1/records/${record.record_id}/approve`, {
    headers: { Origin: "https://evil.example" },
    data: { version: record.version },
  });
  expect(elsewhere.status()).toBe(403);
  expect((await elsewhere.json()).type).toBe("origin_not_allowed");

  const signedOut = await page.context().browser()!.newContext({ baseURL: page.url() });
  for (const path of ["/api/v1/records", "/api/v1/stats", `/api/v1/records/${record.record_id}`]) {
    expect((await signedOut.request.get(path)).status(), path).toBe(401);
  }
  await signedOut.close();
});

test("the sign-in page shows the eye that reveals the password, and a greeting", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator(".login-hint")).toHaveText(/^(בוקר טוב|צהריים טובים|ערב טוב|לילה טוב), טוב לראות אותך\.$/);
  const password = page.getByLabel("סיסמה", { exact: true });
  await password.fill("secret");
  await expect(password).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "הצגת הסיסמה" }).click();
  await expect(password).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "הסתרת הסיסמה" }).click();
  await expect(password).toHaveAttribute("type", "password");
  // Nothing to send without a username.
  await expect(page.getByRole("button", { name: /^כניסה/ })).toBeDisabled();
});
