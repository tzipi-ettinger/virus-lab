// @vitest-environment jsdom
// Approving one record, blocked while a field is flagged (PLAN-DEV-B 3.2, D3).
// Owner: B

import { cleanup, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "../../api/client";
import { ApproveButton } from "./ApproveButton";
import { mutationError, useRecordMutations, type ApiRecord, type Saved } from "./recordMutations";
import { blockingFields, fieldTitle, isReady } from "./reviewRows";
import { field, flagged, record } from "./testRecords";

const flaggedRecord = () =>
  record({
    needs_review: true,
    fields: { ...record().fields, national_id: field("1122", flagged("1122")) },
    central_numbers: [field("948062"), field("12", flagged("12"))],
  });

afterEach(cleanup);

describe("blocking fields", () => {
  test("named as the server names them", () => {
    expect(blockingFields(flaggedRecord())).toEqual(["national_id", "central_numbers[1]"]);
    expect(blockingFields(record())).toEqual([]);
  });

  test("an issue on the whole record shows but doesn't block (#59)", () => {
    const unsure = record({
      needs_review: true,
      issues: [{ code: "PAGE_GROUPING_UNCERTAIN", severity: "warning", message: "יש לבדוק" }],
    });
    expect(isReady(unsure)).toBe(true);
  });

  test("an approved record is not ready again", () => {
    expect(isReady(record({ status: "approved" }))).toBe(false);
  });

  test("in Hebrew", () => {
    expect(["national_id", "central_numbers[1]"].map(fieldTitle)).toEqual(["ת״ז", "מספר מרכזי 2"]);
  });
});

describe("ApproveButton", () => {
  function renderButton(r: ApiRecord, onApprove = vi.fn<(r: ApiRecord) => Promise<Saved>>().mockResolvedValue(null)) {
    render(<ApproveButton record={r} onApprove={onApprove} />);
    return onApprove;
  }

  test("a ready record is approved with one click", async () => {
    const onApprove = renderButton(record());

    await userEvent.setup().click(screen.getByRole("button", { name: "אישור" }));

    expect(onApprove).toHaveBeenCalledOnce();
  });

  test("a flagged record can't be approved and says what to fix", () => {
    renderButton(flaggedRecord());

    const button = screen.getByRole("button", { name: "אישור" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText("לטפל קודם ב: ת״ז, מספר מרכזי 2")).toBeTruthy();
  });

  test("the server's refusal is shown", async () => {
    renderButton(record(), vi.fn<(r: ApiRecord) => Promise<Saved>>().mockResolvedValue("אי אפשר לאשר עדיין"));

    await userEvent.setup().click(screen.getByRole("button", { name: "אישור" }));

    expect(screen.getByRole("alert").textContent).toBe("אי אפשר לאשר עדיין");
  });

  test("an approved record says so instead", () => {
    renderButton(record({ status: "approved" }));

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("✓ אושר")).toBeTruthy();
  });

  test("nothing left to fix turns the button green, and a flagged one stays plain", () => {
    renderButton(record());
    expect(screen.getByRole("button", { name: "אישור" }).className).toBe("is-ready");
    cleanup();

    renderButton(flaggedRecord());
    expect(screen.getByRole("button", { name: "אישור" }).className).toBe("");
  });
});

describe("approve", () => {
  const fetchMock = vi.fn<typeof fetch>();
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  test("sends the version and puts the approved record in place", async () => {
    const approved = record({ status: "approved", version: 4, approved_by: "esty" });
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(approved), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    const onRecords = vi.fn();
    const { result } = renderHook(() => useRecordMutations(onRecords));

    expect(await result.current.approve(record({ version: 3 }))).toBeNull();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/records/r1/approve");
    expect(JSON.parse(String(init?.body))).toEqual({ version: 3 });
    expect(onRecords).toHaveBeenCalledWith([approved]);
  });

  test("review_required names the fields in Hebrew", () => {
    const error = new ApiError(409, {
      type: "review_required",
      title: "x",
      blocking_fields: ["national_id", "central_numbers[0]"],
    });
    expect(mutationError(error)).toBe("אי אפשר לאשר עדיין. יש לטפל קודם ב: ת״ז, מספר מרכזי 1");
  });
});
