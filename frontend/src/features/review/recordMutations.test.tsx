// @vitest-environment jsdom
// Saving corrections: the request, the server's answer, and each conflict (PLAN-DEV-B 3.5).
// Owner: B

import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ApiError } from "../../api/client";
import { record } from "./testRecords";
import {
  VERSION_CONFLICT,
  keepCentrals,
  mutationError,
  useRecordMutations,
  type ApiRecord,
} from "./recordMutations";

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function reply(status: number, body: unknown) {
  const type = status < 400 ? "application/json" : "application/problem+json";
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": type } });
}

function mutations() {
  const onRecords = vi.fn<(records: ApiRecord[]) => void>();
  const { result } = renderHook(() => useRecordMutations(onRecords));
  return { ...result.current, onRecords };
}

const sent = (call = 0) => {
  const [url, init] = fetchMock.mock.calls[call];
  return { url, method: init?.method, body: JSON.parse(String(init?.body)) };
};

describe("useRecordMutations", () => {
  test("a correction sends the value with the record's version", async () => {
    const r = record({ version: 4 });
    fetchMock.mockResolvedValue(reply(200, { record: r, siblings: [] }));
    const { saveField } = mutations();

    expect(await saveField(r, "national_id", { value: "011223344" })).toBeNull();

    expect(sent()).toEqual({
      url: "/api/v1/records/r1",
      method: "PATCH",
      body: { version: 4, fields: { national_id: { value: "011223344" } } },
    });
  });

  test("the record and its siblings from the answer replace the local ones", async () => {
    const saved = record({ version: 5 });
    const sibling = record({ record_id: "r2", commitment_index: 1 });
    fetchMock.mockResolvedValue(reply(200, { record: saved, siblings: [sibling] }));
    const { saveField, onRecords } = mutations();

    await saveField(record(), "last_name", { value: "כהן" });

    expect(onRecords).toHaveBeenCalledWith([saved, sibling]);
  });

  test("a confirmation sends confirmed only", async () => {
    fetchMock.mockResolvedValue(reply(200, { record: record(), siblings: [] }));
    const { saveField } = mutations();

    await saveField(record(), "sender", { confirmed: true });

    expect(sent().body.fields).toEqual({ sender: { confirmed: true } });
  });

  test("central numbers go as the full list", async () => {
    fetchMock.mockResolvedValue(reply(200, { record: record(), siblings: [] }));
    const { saveCentrals } = mutations();

    await saveCentrals(record(), [{ idx: 0 }, { value: "123456" }]);

    expect(sent().body).toEqual({ version: 1, central_numbers: [{ idx: 0 }, { value: "123456" }] });
  });

  test("a stale version reloads the record and says so", async () => {
    const fresh = record({ version: 9 });
    fetchMock
      .mockResolvedValueOnce(reply(409, { type: "version_conflict", title: "x", status: 409 }))
      .mockResolvedValueOnce(reply(200, fresh));
    const { saveField, onRecords } = mutations();

    expect(await saveField(record(), "first_name", { value: "דנה" })).toBe(VERSION_CONFLICT);
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/records/r1");
    expect(onRecords).toHaveBeenCalledWith([fresh]);
  });
});

describe("keepCentrals", () => {
  test("keeps every item by its position, with one change", () => {
    const r = record();
    expect(keepCentrals(r, { 1: { confirmed: true } })).toEqual([{ idx: 0 }, { idx: 1, confirmed: true }]);
  });
});

describe("mutationError", () => {
  test.each([
    ["record_approved", "כבר אושרה"],
    ["sibling_approved", "רשומה אחרת מאותו טופס"],
  ])("%s says why the change can't be made", (type, text) => {
    expect(mutationError(new ApiError(409, { type, title: "x" }))).toContain(text);
  });

  test("anything else uses the server's title", () => {
    expect(mutationError(new ApiError(422, { type: "validation", title: "אין מספר מרכזי במקום הזה" }))).toBe(
      "אין מספר מרכזי במקום הזה",
    );
  });
});
