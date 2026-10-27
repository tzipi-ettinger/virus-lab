// The overview's numbers are the server's (GET /stats), and every screen that loads
// data says what went wrong when the server fails or the connection drops, with a
// "try again" that works.
// Owner: shared

import {
  FIELD_TITLES,
  RUN,
  expect,
  requirePassword,
  signIn,
  signedInRequest,
  test,
  uploadViaApi,
  type ApiRecord,
} from "./helpers";
import type { Page } from "@playwright/test";

interface Stats {
  pending: number;
  approved: number;
  needs_review: number;
  fields_total: number;
  fields_flagged: number;
  corrections: number;
  corrected_records: number;
  by_field: { field: string; corrections: number }[];
}

let record: ApiRecord;

test.beforeAll(async () => {
  requirePassword();
  const request = await signedInRequest();
  [record] = await uploadViaApi(request, `e2e-stats-${RUN}.pdf`, 3);
  await request.dispose();
});

const fieldTitle = (field: string) => (field === "central_numbers" ? "מספר מרכזי" : (FIELD_TITLES[field] ?? field));

test("the overview's numbers are the server's", async ({ page }) => {
  await signIn(page);
  await page.goto("/stats");
  const stats = (await (await page.request.get("/api/v1/stats")).json()) as Stats;
  const total = stats.pending + stats.approved;
  const ready = stats.pending - stats.needs_review;
  const percent = (part: number, whole: number) =>
    page.evaluate(
      ([p, w]) => new Intl.NumberFormat("he-IL", { style: "percent", maximumFractionDigits: 1 }).format(w ? p / w : 0),
      [part, whole],
    );

  await expect(page.locator(".stats-total")).toHaveText(`${total} רשומות במערכת`);

  const pending = page.getByRole("region", { name: "ממתינות לאישור" });
  await expect(pending.locator(".stats-number")).toHaveText(String(stats.pending));
  await expect(pending.locator(".stats-chip.is-ready")).toHaveText(`${ready} מוכנות לאישור`);
  if (stats.needs_review > 0) {
    await expect(pending.locator(".stats-chip.is-review")).toHaveText(`${stats.needs_review} דורשות בדיקה`);
  }

  const flagged = page.getByRole("region", { name: "שדות שסומנו לבדיקה" });
  await expect(flagged.locator(".stats-number")).toHaveText(await percent(stats.fields_flagged, stats.fields_total));
  await expect(flagged.locator(".stats-note")).toHaveText(
    `${stats.fields_flagged} מתוך ${stats.fields_total} שדות ברשומות שעוד לא אושרו`,
  );

  const fixed = page.getByRole("region", { name: "תיקונים ידניים" });
  await expect(fixed.locator(".stats-number")).toHaveText(String(stats.corrections));
  const chart = page.getByRole("region", { name: "השדות שתוקנו הכי הרבה" });
  if (stats.corrections === 0) {
    await expect(fixed.locator(".stats-note")).toHaveText("עוד לא תוקן אף שדה");
    await expect(chart).toContainText("עוד לא תוקנו שדות");
  } else {
    await expect(fixed.locator(".stats-note")).toHaveText(
      `ב־${stats.corrected_records} רשומות. השדה שתוקן הכי הרבה: ${fieldTitle(stats.by_field[0].field)}`,
    );
    await expect(chart.getByRole("listitem")).toHaveText(
      stats.by_field.map((f) => `${fieldTitle(f.field)}${f.corrections}`),
    );
  }

  const status = page.getByRole("region", { name: "מצב כל הרשומות" });
  await expect(status.getByRole("img")).toHaveAttribute(
    "aria-label",
    `${stats.approved} מאושרות, ${ready} מוכנות לאישור, ${stats.needs_review} דורשות בדיקה`,
  );
  await expect(status.locator(".stats-legend strong")).toHaveText([
    String(stats.approved),
    String(ready),
    String(stats.needs_review),
  ]);
  await expect(status.locator(".stats-ring-hole strong")).toHaveText(await percent(stats.approved, total));
});

test("the overview's link opens the pending records", async ({ page }) => {
  await signIn(page);
  await page.goto("/stats");
  await page.getByRole("link", { name: "לרשימת הממתינות ←" }).click();
  await expect(page).toHaveURL(/\/records\?status=pending$/);
  await expect(page.getByRole("group", { name: "מונים" }).getByRole("button", { name: /ממתינות/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
});

const PROBLEM = { type: "server_error", title: "תקלה בשרת", status: 500 };

/** The first answer to `url` fails as `how`; "נסי שוב" then loads it for real. */
async function failsThenRecovers(page: Page, path: string, url: string, how: "500" | "offline", loaded: () => Promise<void>) {
  await page.route(
    url,
    (route) =>
      how === "offline"
        ? route.abort("internetdisconnected")
        : route.fulfill({ status: 500, contentType: "application/problem+json", body: JSON.stringify(PROBLEM) }),
    { times: 1 },
  );
  await page.goto(path);
  const alert = page.getByRole("alert");
  await expect(alert).toContainText(how === "offline" ? "אין חיבור לשרת. בדקי את החיבור ונסי שוב" : "תקלה בשרת");
  await alert.getByRole("button", { name: "נסי שוב" }).click();
  await expect(alert).toHaveCount(0);
  await loaded();
}

for (const how of ["500", "offline"] as const) {
  test(`when the server ${how === "500" ? "fails" : "can't be reached"}, each screen says so and "try again" works`, async ({
    page,
  }) => {
    await signIn(page);
    await failsThenRecovers(page, "/stats", "**/api/v1/stats", how, () =>
      expect(page.getByRole("region", { name: "ממתינות לאישור" })).toBeVisible(),
    );
    await failsThenRecovers(page, "/records", "**/api/v1/records?*", how, () =>
      expect(page.locator(".records-table tbody tr").first()).toBeVisible(),
    );
    await failsThenRecovers(page, `/records/${record.record_id}`, `**/api/v1/records/${record.record_id}`, how, () =>
      expect(page.locator(".record-fields")).toBeVisible(),
    );
  });
}
