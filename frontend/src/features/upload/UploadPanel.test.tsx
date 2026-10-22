// @vitest-environment jsdom
// UploadPanel: what each file's row says, retry, failed pages, and how files get in.
// useExtract (the sending itself) has its own tests; here it is a stub that hands
// the panel a list of items. UploadPanel.progress.test.tsx runs the real hook.
// Owner: A

import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { ExtractResponse, UploadItem } from "./useExtract";
import { UploadPanel } from "./UploadPanel";

const hook = vi.hoisted(() => ({
  items: [] as unknown[],
  add: undefined as unknown as (files: File[]) => void,
  retry: undefined as unknown as (key: string) => void,
}));

vi.mock("./useExtract", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./useExtract")>()),
  useExtract: () => ({ items: hook.items, add: hook.add, retry: hook.retry }),
}));

beforeEach(() => {
  hook.items = [];
  hook.add = vi.fn();
  hook.retry = vi.fn();
});
afterEach(() => {
  cleanup();
});

const pdf = (name = "scan.pdf") => new File(["%PDF"], name, { type: "application/pdf" });

function result(over: Partial<ExtractResponse> = {}): ExtractResponse {
  return {
    files: [{ file_id: "f1", filename: "scan.pdf", page_count: 3, status: "ok", error: null }],
    records: [{}, {}] as ExtractResponse["records"],
    failed_pages: [],
    quota_exhausted: false,
    ...over,
  };
}

function item(over: Partial<UploadItem>): UploadItem {
  return { key: "k1", file: pdf(), status: "queued", canRetry: false, ...over };
}

const row = (name: string) => screen.getByText(name).closest("li") as HTMLElement;

describe("UploadPanel", () => {
  test("with no files, the drop zone shows, and no file list", () => {
    render(<UploadPanel onResult={() => {}} />);

    expect(screen.getByRole("heading", { name: "העלאת טפסי התחייבות" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "בחירת קבצים" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "הקבצים שלך" })).toBeNull();
    expect(screen.queryByText(/מתוך .* קבצים/)).toBeNull();
  });

  test("a read file says how many pages and records, and the summary adds them up", () => {
    hook.items = [
      item({ key: "a", file: pdf("a.pdf"), status: "done", result: result() }),
      item({
        key: "b",
        file: pdf("b.pdf"),
        status: "done",
        result: result({
          files: [{ file_id: "f2", filename: "b.pdf", page_count: 1, status: "ok", error: null }],
          records: [{}] as ExtractResponse["records"],
        }),
      }),
      item({ key: "c", file: pdf("c.pdf"), status: "queued" }),
    ];
    render(<UploadPanel onResult={() => {}} />);

    expect(within(row("a.pdf")).getByText("נקרא")).toBeTruthy();
    expect(row("a.pdf").textContent).toContain("3 עמודים · 2 רשומות");
    expect(row("b.pdf").textContent).toContain("עמוד אחד · רשומה אחת");
    expect(within(row("c.pdf")).getByText("ממתין")).toBeTruthy();
    expect(screen.getByText(/2 מתוך 3 קבצים/).textContent).toContain("נוצרו 3 רשומות");
  });

  test("a sending file shows the pages read and a bar, without a clock", () => {
    hook.items = [item({ status: "sending", progress: { done: 2, total: 8 } })];
    render(<UploadPanel onResult={() => {}} />);

    expect(within(row("scan.pdf")).getByText("נקרא…")).toBeTruthy();
    expect(row("scan.pdf").textContent).toContain("נקראו 2 מתוך 8 עמודים");
    const bar = row("scan.pdf").querySelector(".upload-progress-bar") as HTMLElement;
    expect(bar.style.inlineSize).toBe("25%");
    expect(row("scan.pdf").textContent).not.toMatch(/\d:\d\d/);
  });

  test("a sending file with no page count yet shows no bar", () => {
    hook.items = [item({ status: "sending" })];
    render(<UploadPanel onResult={() => {}} />);

    expect(within(row("scan.pdf")).getByText("נקרא…")).toBeTruthy();
    expect(row("scan.pdf").querySelector(".upload-progress-bar")).toBeNull();
  });

  test("a failed file shows its message and offers to send it again", async () => {
    hook.items = [item({ status: "failed", message: "Gemini לא ענה בזמן", canRetry: true })];
    render(<UploadPanel onResult={() => {}} />);

    expect(within(row("scan.pdf")).getByText("נכשל")).toBeTruthy();
    expect(row("scan.pdf").textContent).toContain("Gemini לא ענה בזמן");
    await userEvent.click(screen.getByRole("button", { name: "נסי שוב" }));

    expect(hook.retry).toHaveBeenCalledWith("k1");
  });

  test("a file that can't be sent again has no retry button", () => {
    hook.items = [item({ status: "partial", result: result({ quota_exhausted: true }) })];
    render(<UploadPanel onResult={() => {}} />);

    expect(within(row("scan.pdf")).getByText("נקרא חלקית")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "נסי שוב" })).toBeNull();
  });

  test("failed pages are listed with the file, the page and the reason", () => {
    hook.items = [
      item({
        status: "partial",
        result: result({
          failed_pages: [
            {
              file_id: "f1",
              source_file: "scan.pdf",
              page_number: 2,
              error: { code: "EXTRACTION_FAILED", message: "התשובה לא תקינה" },
            },
          ],
        }),
      }),
    ];
    render(<UploadPanel onResult={() => {}} />);

    const failed = screen.getByRole("region", { name: "עמודים שלא נקראו (1)" });
    expect(failed.textContent).toContain("scan.pdf, עמוד 2: התשובה לא תקינה");
  });

  test("a cut connection warns to check the records before sending again", () => {
    hook.items = [item({ status: "interrupted" })];
    render(<UploadPanel onResult={() => {}} />);

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("החיבור נקטע");
    expect(within(alert).getByRole("link", { name: "במסך הרשומות" }).getAttribute("href")).toBe("/records");
    expect(within(row("scan.pdf")).getByText("החיבור נקטע")).toBeTruthy();
  });

  test("chosen files go to the upload, and the input is cleared for the same file again", async () => {
    const { container } = render(<UploadPanel onResult={() => {}} />);
    const input = container.querySelector("input[type=file]") as HTMLInputElement;
    const file = pdf();

    await userEvent.upload(input, file);

    expect(hook.add).toHaveBeenCalledWith([file]);
    expect(input.value).toBe("");
  });

  test("the button opens the file picker", async () => {
    const { container } = render(<UploadPanel onResult={() => {}} />);
    const input = container.querySelector("input[type=file]") as HTMLInputElement;
    const click = vi.spyOn(input, "click");

    await userEvent.click(screen.getByRole("button", { name: "בחירת קבצים" }));

    expect(click).toHaveBeenCalled();
  });

  test("dropped files go to the upload, and the zone lights up while dragging", () => {
    const { container } = render(<UploadPanel onResult={() => {}} />);
    const zone = container.querySelector(".upload-drop") as HTMLElement;
    const file = pdf();

    fireEvent.dragOver(zone);
    expect(zone.className).toContain("is-dragging");
    fireEvent.dragLeave(zone);
    expect(zone.className).not.toContain("is-dragging");

    fireEvent.dragOver(zone);
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    expect(zone.className).not.toContain("is-dragging");
    expect(hook.add).toHaveBeenCalledWith([file]);
  });

  test("tells the page when files are being sent and when they are done", () => {
    const onBusyChange = vi.fn();
    hook.items = [item({ status: "sending" })];
    const { rerender } = render(<UploadPanel onResult={() => {}} onBusyChange={onBusyChange} />);
    expect(onBusyChange).toHaveBeenLastCalledWith(true);

    hook.items = [item({ status: "done", result: result() })];
    rerender(<UploadPanel onResult={() => {}} onBusyChange={onBusyChange} />);
    expect(onBusyChange).toHaveBeenLastCalledWith(false);
  });
});
