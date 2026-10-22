// @vitest-environment jsdom
// While a file is read: the pages read so far and a bar, and no clock (22.10).
// Owner: A

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { UploadPanel } from "./UploadPanel";
import { EXTRACT_URL, POLL_MS } from "./useExtract";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("a file being read shows its pages and a bar, without a clock", async () => {
  vi.useFakeTimers();
  // The upload is taken (202), and its job is still being read.
  const job = { job_id: "job-1", status: "running", done: 3, total: 10, result: null, problem: null };
  vi.stubGlobal("fetch", (url: string) =>
    Promise.resolve(new Response(JSON.stringify(job), { status: url === EXTRACT_URL ? 202 : 200 })),
  );
  const { container } = render(<UploadPanel onResult={() => {}} />);

  const pdf = new File(["%PDF"], "a.pdf", { type: "application/pdf" });
  fireEvent.change(container.querySelector("input[type=file]")!, { target: { files: [pdf] } });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(POLL_MS);
  });

  const sending = container.querySelector(".upload-sending")!;
  expect(sending.textContent).toBe("נקראו 3 מתוך 10 עמודים");
  expect((container.querySelector(".upload-progress-bar") as HTMLElement).style.inlineSize).toBe("30%");
  expect(screen.queryByText(/\d:\d\d/)).toBeNull();
});
