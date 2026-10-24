// Shared by the specs: signing in, uploading through the API (for specs that need
// records but don't test the upload), and a `test` that fails on any error in the
// page. Expectations come from the server's own answers, not from a fixed database,
// so the specs pass on a fresh database (CI) and on one that already has records.
// Owner: shared

import {
  expect,
  request as apiRequest,
  test as base,
  type APIRequestContext,
  type Locator,
  type Page,
} from "@playwright/test";
import { blankPdf } from "./blankPdf";

export const USER = process.env.E2E_USER ?? "e2e";
export const PASSWORD = process.env.E2E_PASSWORD ?? "";
export const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:8000";

/** This run's own file names, apart from earlier runs on the same database. */
export const RUN = Date.now().toString(36);

export interface ApiField {
  value: string | null;
  needs_review: boolean;
  corrected: boolean;
  confirmed: boolean;
  issues: { code: string }[];
}

export interface ApiRecord {
  record_id: string;
  status: "pending" | "approved";
  version: number;
  source_file: string;
  page_number: number;
  approved_by: string | null;
  fields: Record<string, ApiField>;
  central_numbers: ApiField[];
}

export interface RecordSummary {
  record_id: string;
  status: "pending" | "approved";
  needs_review: boolean;
  sender: string | null;
  commitment_number: string | null;
  received_date: string | null;
}

export interface RecordList {
  items: RecordSummary[];
  total: number;
  counts: { pending: number; approved: number; needs_review: number };
}

/** Errors in the page fail the test: an uncaught exception, or a console error that is
 *  not a failed request (a 401 before signing in, a 500 a test sends on purpose). */
export const test = base.extend<{ pageErrors: string[] }>({
  pageErrors: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
      page.on("console", (message) => {
        if (message.type() === "error" && !message.text().startsWith("Failed to load resource")) {
          errors.push(`console: ${message.text()}`);
        }
      });
      await use(errors);
      expect(errors, "errors in the page").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

export function requirePassword() {
  if (!PASSWORD) throw new Error("Set E2E_PASSWORD to the password of E2E_USER (default: e2e)");
}

export async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("שם משתמש").fill(USER);
  await page.getByLabel("סיסמה", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: /^כניסה/ }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

export function pdfFile(name: string, pages = 1) {
  return { name, mimeType: "application/pdf", buffer: blankPdf(pages) };
}

/** A request context of its own, signed in: for beforeAll, where there is no page. It
 *  sends Origin as the page does: the server refuses a change from anywhere else. */
export async function signedInRequest(): Promise<APIRequestContext> {
  const request = await apiRequest.newContext({ baseURL: BASE_URL, extraHTTPHeaders: { Origin: BASE_URL } });
  const answer = await request.post("/api/v1/auth/login", { data: { username: USER, password: PASSWORD } });
  expect(answer.ok(), "signing in through the API").toBe(true);
  return request;
}

/** Uploads a blank PDF and waits for its job: the records the server saved. */
export async function uploadViaApi(request: APIRequestContext, name: string, pages = 1): Promise<ApiRecord[]> {
  const started = await request.post("/api/v1/extract", { multipart: { files: pdfFile(name, pages) } });
  expect(started.status(), "the upload is accepted").toBe(202);
  let job = (await started.json()) as { job_id: string; status: string; result?: { records: ApiRecord[] } };
  await expect
    .poll(
      async () => {
        job = await (await request.get(`/api/v1/extract/jobs/${job.job_id}`)).json();
        return job.status;
      },
      { timeout: 60_000 },
    )
    .toBe("done");
  return job.result?.records ?? [];
}

export async function getRecord(request: APIRequestContext, id: string): Promise<ApiRecord> {
  const answer = await request.get(`/api/v1/records/${id}`);
  expect(answer.ok(), `GET record ${id}`).toBe(true);
  return answer.json();
}

export async function listRecords(request: APIRequestContext, query = ""): Promise<RecordList> {
  const answer = await request.get(`/api/v1/records?limit=50${query ? `&${query}` : ""}`);
  expect(answer.ok(), `GET records ${query}`).toBe(true);
  return answer.json();
}

/** Something still blocks approval: a flagged field or central number. */
export function blocked(record: ApiRecord): boolean {
  return [...Object.values(record.fields), ...record.central_numbers].some((f) => f.needs_review);
}

/** The review screen's names for the fields. */
export const FIELD_TITLES: Record<string, string> = {
  national_id: "ת״ז",
  first_name: "שם פרטי",
  last_name: "שם משפחה",
  commitment_number: "מספר התחייבות",
  sender: "גורם שולח",
  received_date: "תאריך קבלה",
};

const recent = new Date(Date.now() - 3 * 24 * 3600 * 1000);
const pad = (n: number) => String(n).padStart(2, "0");

/** A value the rules accept for each field, as a reviewer would type it. The
 *  commitment number is this run's own, so it is never a duplicate. */
export const GOOD_VALUES: Record<string, string> = {
  first_name: "בדיקה",
  last_name: "לוי",
  national_id: "011223344",
  commitment_number: String(Date.now()).slice(-9),
  received_date: `${pad(recent.getDate())}/${pad(recent.getMonth() + 1)}/${recent.getFullYear()}`,
  sender: "מכבי",
};

/** Flags a reviewer clears by confirming the value as it is. */
export const CONFIRMABLE = new Set(["DUPLICATE_RECORD", "DATE_OUT_OF_RANGE"]);

/** Every flag is on a field the specs know how to fix (not a central number). */
export function fixable(record: ApiRecord): boolean {
  return (
    blocked(record) &&
    !record.central_numbers.some((f) => f.needs_review) &&
    Object.entries(record.fields).every(([name, f]) => !f.needs_review || name in GOOD_VALUES)
  );
}

/**
 * Clears every flag the way a reviewer would, in the fields shown inside `fields`
 * (the review panel or the record page): a value that only needs a look is
 * confirmed, anything else gets a good value typed in, or picked for the sender.
 */
export async function fixFlagged(fields: Locator, record: ApiRecord) {
  for (const [name, field] of Object.entries(record.fields)) {
    if (!field.needs_review) continue;
    const title = FIELD_TITLES[name];
    // Typing the value it already has changes nothing, so that one is confirmed too.
    if (field.value && (field.value === GOOD_VALUES[name] || field.issues.every((i) => CONFIRMABLE.has(i.code)))) {
      await fields.getByRole("button", { name: `אישור ערך: ${title}` }).click();
      await expect(fields.getByRole("button", { name: `אישור ערך: ${title}` })).toHaveCount(0);
      continue;
    }
    await fields.getByRole("button", { name: new RegExp(`^${title}: `) }).click();
    const editor = fields.getByLabel(`עריכת ${title}`);
    if (name === "sender") await editor.selectOption(GOOD_VALUES.sender);
    else {
      await editor.fill(GOOD_VALUES[name]);
      await editor.press("Enter");
    }
    await expect(editor).toHaveCount(0); // saved: the editor closes
  }
}

/** dd/mm/yyyy → a sortable number, or null for "—". */
export function dateKey(text: string): number | null {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text.trim());
  return match ? Number(`${match[3]}${match[2]}${match[1]}`) : null;
}
