// The upload and review screen, through the real server: an 8-page file reads every
// fixture (one of them a failed read), then a record is fixed, approved and undone,
// another is deleted and undone, and "approve all ready" approves a third. Each step
// is checked on the server too, not only on the screen.
// Owner: shared

import {
  RUN,
  blocked,
  expect,
  fixFlagged,
  fixable,
  getRecord,
  pdfFile,
  requirePassword,
  signIn,
  test,
  type ApiRecord,
} from "./helpers";

test.beforeAll(requirePassword);

const UNDO_WAIT = 6_000; // a little over UNDO_MS (useUndo.ts): the change is sent after it

test("upload a file with every kind of page, then fix, approve and delete, with undo", async ({ page }) => {
  test.setTimeout(180_000);
  const name = `e2e-review-${RUN}.pdf`;
  // The records the server saved, from the job's answer, in the order the table shows them.
  const saved: ApiRecord[] = [];
  page.on("response", async (response) => {
    if (!response.url().includes("/api/v1/extract/jobs/")) return;
    const job = await response.json().catch(() => null);
    if (job?.status === "done") saved.push(...(job.result?.records ?? []));
  });

  await signIn(page);
  await expect(page).toHaveURL(/\/upload$/);
  const rows = page.locator(".review-table tbody tr");
  const panel = page.locator(".record-panel");
  const toast = page.locator(".undo-toast");
  const open = async (index: number) => {
    await rows.nth(index).locator(".review-select").click();
    await expect(rows.nth(index)).toHaveAttribute("aria-selected", "true");
  };

  await test.step("the file is read page by page, and the list opens by itself", async () => {
    await expect(page.getByText("גררי לכאן קבצי PDF או תמונות")).toBeVisible();
    await page.locator("input[type=file]").setInputFiles(pdfFile(name, 8));
    const item = page.locator(".upload-item", { hasText: name });
    await expect(item).toHaveClass(/is-done/, { timeout: 90_000 });
    await expect(item).toContainText("8 עמודים");
    await expect.poll(() => saved.length).toBeGreaterThan(2);
    await expect(page.getByRole("heading", { name: /טבלת בדיקה/ })).toBeVisible();
    await expect(rows).toHaveCount(saved.length);
  });

  await test.step("the head counts what is left to fix, and nothing is approved yet", async () => {
    const toFix = saved.filter(blocked).length;
    await expect(page.locator(".review-head")).toContainText(`${saved.length} רשומות · ${toFix} לתיקון`);
    await expect(page.locator(".review-progress-text")).toHaveText(`0 מתוך ${saved.length} אושרו`);
    await expect(rows.first()).toHaveAttribute("aria-selected", "true");
  });

  await test.step("the failed page is listed with its message, and the upload is one click away", async () => {
    await page.getByRole("button", { name: "+ העלאת קבצים נוספים" }).click();
    await expect(page.getByRole("heading", { name: /עמודים שלא נקראו \(1\)/ })).toBeVisible();
    await expect(page.locator(".upload-failed li")).toContainText(name);
    await expect(page.locator(".upload-summary")).toContainText("1 מתוך 1 קבצים");
    await page.getByRole("button", { name: `לרשימת הרשומות (${saved.length}) ←` }).click();
    await expect(rows).toHaveCount(saved.length);
  });

  await test.step("the arrow keys move through the list", async () => {
    await rows.first().locator(".review-select").focus();
    await page.keyboard.press("ArrowDown");
    await expect(rows.nth(1)).toHaveAttribute("aria-selected", "true");
    await page.keyboard.press("ArrowUp");
    await expect(rows.first()).toHaveAttribute("aria-selected", "true");
  });

  await test.step("the original page shows beside the fields, and a field is pointed out on it", async () => {
    await expect(panel.getByRole("heading", { name: "הטופס המקורי" })).toBeVisible();
    const image = panel.locator(".preview-image");
    await expect(image).toBeVisible();
    await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
    await panel.locator(".record-panel-fields tr").first().hover();
    await expect(panel.locator(".preview-highlight")).toHaveText(/מסומן בתמונה|נקרא בעמוד|אין סימון בתמונה ל/);
  });

  const target = saved.findIndex(fixable);
  expect(target, "a record with flags the spec knows how to fix").toBeGreaterThanOrEqual(0);
  const record = saved[target];

  await test.step("a field is edited in place and saved on the server", async () => {
    await open(target);
    await panel.getByRole("button", { name: /^שם פרטי: / }).click();
    await panel.getByLabel("עריכת שם פרטי").fill("בדיקה");
    await panel.getByLabel("עריכת שם פרטי").press("Enter");
    await expect(panel.getByRole("button", { name: /^שם פרטי: בדיקה, תוקן\. לעריכה$/ })).toBeVisible();
    const after = await getRecord(page.request, record.record_id);
    expect(after.fields.first_name).toMatchObject({ value: "בדיקה", corrected: true });
  });

  await test.step("the ID is checked while typing, and Escape leaves it as it was", async () => {
    const before = (await getRecord(page.request, record.record_id)).fields.national_id.value;
    await panel.getByRole("button", { name: /^ת״ז: / }).click();
    const input = panel.getByLabel("עריכת ת״ז");
    await input.fill("123456789");
    await expect(panel.locator(".review-cell-hint")).toHaveText(/ספרת הביקורת לא מתאימה/);
    await input.press("Escape");
    await expect(input).toHaveCount(0);
    expect((await getRecord(page.request, record.record_id)).fields.national_id.value).toBe(before);
  });

  await test.step("fixing each flagged field leaves nothing to fix, here and on the server", async () => {
    await fixFlagged(panel, await getRecord(page.request, record.record_id));
    await expect(panel.locator(".record-panel-summary")).toHaveText(/הכל תקין\. אפשר לאשר/);
    expect(blocked(await getRecord(page.request, record.record_id))).toBe(false);
    await expect(rows.nth(target)).toContainText("מוכן לאישור");
  });

  await test.step("approve, then undo: nothing is sent", async () => {
    await panel.getByRole("button", { name: "אישור", exact: true }).click();
    await expect(toast).toContainText(/אושרה/);
    await toast.getByRole("button", { name: "ביטול" }).click();
    await expect(toast).toHaveCount(0);
    await page.waitForTimeout(UNDO_WAIT);
    expect((await getRecord(page.request, record.record_id)).status).toBe("pending");
  });

  await test.step("approve again: once the undo runs out it is approved on the server", async () => {
    await open(target);
    await panel.getByRole("button", { name: "אישור", exact: true }).click();
    await expect(toast).toContainText("הרשומה של בדיקה");
    await expect
      .poll(async () => (await getRecord(page.request, record.record_id)).status, { timeout: 15_000 })
      .toBe("approved");
    await expect(rows.nth(target)).toContainText("✓ אושר");
    await expect(page.locator(".review-progress-text")).toHaveText(`1 מתוך ${saved.length} אושרו`);
  });

  // Another pending record, to delete.
  const doomedIndex = saved.findIndex((_, i) => i !== target);
  const doomed = saved[doomedIndex];

  await test.step("delete, then undo: the record comes back and stays on the server", async () => {
    await open(doomedIndex);
    await panel.getByRole("button", { name: "מחיקה" }).click();
    await expect(toast).toContainText(/נמחקה/);
    await expect(rows).toHaveCount(saved.length - 1);
    await toast.getByRole("button", { name: "ביטול" }).click();
    await expect(rows).toHaveCount(saved.length);
    await page.waitForTimeout(UNDO_WAIT);
    expect((await page.request.get(`/api/v1/records/${doomed.record_id}`)).status()).toBe(200);
  });

  await test.step("delete again: once the undo runs out it is gone from the server", async () => {
    await open(doomedIndex);
    await panel.getByRole("button", { name: "מחיקה" }).click();
    await expect
      .poll(async () => (await page.request.get(`/api/v1/records/${doomed.record_id}`)).status(), { timeout: 15_000 })
      .toBe(404);
    await expect(rows).toHaveCount(saved.length - 1);
  });

  // The table now holds every record but the deleted one, in the same order.
  const left = saved.filter((r) => r.record_id !== doomed.record_id);
  const third = left.findIndex((r) => r.record_id !== record.record_id && fixable(r));

  await test.step("a fixed record is approved by 'approve all ready'", async () => {
    test.skip(third < 0, "no third record the spec knows how to fix");
    await open(third);
    await fixFlagged(panel, await getRecord(page.request, left[third].record_id));
    const all = page.getByRole("button", { name: /^✓ אשרי את כל המוכנות \(\d+\)$/ });
    const ready = Number(/\((\d+)\)/.exec((await all.textContent()) ?? "")?.[1]);
    expect(ready).toBeGreaterThanOrEqual(1);
    await all.click();
    await expect(page.locator(".review-summary")).toHaveText(new RegExp(`^אושרו ${ready} רשומות\\.`));
    expect((await getRecord(page.request, left[third].record_id)).status).toBe("approved");
  });

  await test.step("'next to fix' opens a record that still has something to fix", async () => {
    const pending = left.findIndex((r) => blocked(r) && r.record_id !== record.record_id);
    test.skip(pending < 0, "nothing left to fix");
    await open(left.findIndex((r) => r.record_id === record.record_id));
    await panel.getByRole("button", { name: "הבאה לתיקון ←" }).click();
    await expect(page.locator(".review-table tbody tr[aria-selected=true]")).toContainText("לתיקון");
  });
});
