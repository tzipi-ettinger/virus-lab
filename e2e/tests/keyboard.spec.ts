// Keyboard: every screen works without a mouse (WCAG 2.0).
//   2.4.1 (A)  on the screens with the navigation, Tab's first stop is the skip
//              link, and it takes focus past the header;
//   2.4.7 (AA) every stop Tab reaches shows that it has focus;
//   2.1.2 (A)  Tab always moves on: nothing holds focus.
// Whether the order of the stops makes sense still needs a person.
// Owner: shared

import { expect, test, type Page } from "@playwright/test";
import { blankPdf } from "./blankPdf";
import { requirePassword, signIn } from "./session";

const FORMS = { name: "e2e-keyboard.pdf", mimeType: "application/pdf", buffer: blankPdf(2) };
// Enough for the header, the controls and the first rows of a table.
const MAX_STOPS = 40;
// Tab inside one element: a date field's day, month and year are three presses.
// More than this many in a row on one element is a trap.
const MAX_PRESSES_INSIDE = 5;

test.beforeAll(requirePassword);
test.use({ reducedMotion: "reduce" });
test.setTimeout(120_000);

interface Stop {
  name: string;
  /** Whether the element, or a box around it, looked different with focus. */
  showedFocus: boolean;
  stuck: boolean;
}

/**
 * Presses Tab up to MAX_STOPS times. Each stop's look (the element and two boxes
 * around it, for :focus-within) is kept while it has focus and compared after the
 * next Tab has taken focus away: a real Tab, not blur(), so no onBlur runs early.
 */
async function walkTabStops(page: Page): Promise<Stop[]> {
  const stops: Stop[] = [];
  for (let i = 0; i <= MAX_STOPS; i++) {
    const step = await page.evaluate(({ first, maxInside }) => {
      type Kept = { element: Element; boxes: Element[]; look: string; name: string; presses: number };
      const holder = window as unknown as { keyboardKept?: Kept };
      // A screen reached without loading the page (upload, then review) would still
      // hold the last stop of the screen before.
      if (first) delete holder.keyboardKept;
      // Focus styles as they rest, not partway through a transition.
      for (const animation of document.getAnimations()) if (animation instanceof CSSTransition) animation.finish();
      const lookOf = (boxes: Element[]) =>
        boxes
          .map((box) => {
            const s = getComputedStyle(box);
            return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow, s.borderColor, s.backgroundColor, s.color, s.textDecorationLine].join(" ");
          })
          .join(" | ");

      const before = holder.keyboardKept;
      const active = document.activeElement;
      if (before && active === before.element) {
        // Still inside the same element (a date field's parts): not a new stop yet.
        before.presses += 1;
        if (before.presses <= maxInside) return null;
        delete holder.keyboardKept;
        return { name: before.name, showedFocus: true, stuck: true };
      }
      const result = before ? { name: before.name, showedFocus: lookOf(before.boxes) !== before.look, stuck: false } : null;

      if (active && active !== document.body) {
        const boxes = [active, active.parentElement, active.parentElement?.parentElement].filter((box): box is Element => !!box);
        const label = active.getAttribute("aria-label") ?? active.textContent ?? "";
        const name = `<${active.tagName.toLowerCase()}${active.className ? `.${String(active.className).split(" ")[0]}` : ""}> ${label.trim().slice(0, 30)}`;
        holder.keyboardKept = { element: active, boxes, look: lookOf(boxes), name, presses: 0 };
      } else {
        delete holder.keyboardKept; // focus left the page: Tab goes round to the top
      }
      return result;
    }, { first: i === 0, maxInside: MAX_PRESSES_INSIDE });
    if (step) stops.push(step);
    if (i < MAX_STOPS) await page.keyboard.press("Tab");
  }
  return stops;
}

async function expectKeyboardUsable(page: Page, screen: string) {
  await page.waitForLoadState("networkidle");
  const stops = await walkTabStops(page);
  expect(stops.length, `${screen}: Tab reached nothing`).toBeGreaterThan(0);
  // Once each: Tab goes round the screen, so a stop can come up more than once.
  const names = (found: Stop[]) => [...new Set(found.map((s) => s.name))];
  expect.soft(names(stops.filter((s) => !s.showedFocus)), `${screen}: no visible focus`).toEqual([]);
  expect.soft(names(stops.filter((s) => s.stuck)), `${screen}: Tab stayed put`).toEqual([]);
}

test("the skip link is the first stop and moves past the header", async ({ page }) => {
  await page.goto("/login");
  await signIn(page);
  await expect(page).toHaveURL(/\/upload$/);

  await page.goto("/records");
  await page.waitForLoadState("networkidle");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "דלג לתוכן הראשי" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();

  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  await expect(page).toHaveURL(/\/records$/); // no "#main" left in the address
  await page.keyboard.press("Tab");
  const next = await page.evaluate(() => !!document.activeElement?.closest("main"));
  expect(next, "the stop after the skip link is in the screen, not the header").toBe(true);
});

test("every screen can be used with Tab alone", async ({ page }) => {
  await page.goto("/login");
  await expectKeyboardUsable(page, "login");

  await signIn(page);
  await expect(page).toHaveURL(/\/upload$/);
  await page.goto("/upload");
  await expectKeyboardUsable(page, "upload");

  await page.locator("input[type=file]").setInputFiles(FORMS);
  await expect(page.locator(".upload-item", { hasText: FORMS.name })).toHaveClass(/is-done/, { timeout: 60_000 });
  await expect(page.getByRole("table").first()).toBeVisible();
  await expectKeyboardUsable(page, "review");

  await page.goto("/records");
  await expect(page.getByRole("row").nth(1)).toBeVisible();
  await expectKeyboardUsable(page, "records");

  await page.getByRole("row").nth(1).getByRole("link").first().click();
  await expect(page).toHaveURL(/\/records\/[^/?]+$/);
  await expectKeyboardUsable(page, "record");

  await page.goto("/stats");
  await expectKeyboardUsable(page, "stats");

  await page.goto("/");
  await expectKeyboardUsable(page, "landing");

  await page.goto("/no-such-page");
  await expectKeyboardUsable(page, "not found");
});
