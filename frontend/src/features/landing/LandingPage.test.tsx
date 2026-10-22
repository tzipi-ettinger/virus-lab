// @vitest-environment jsdom
// The landing page: the ministry's logo and the way in to the upload.
// Owner: shared

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test } from "vitest";
import { LandingPage } from "./LandingPage";

afterEach(cleanup);

describe("LandingPage", () => {
  test("shows the logo and leads to the upload", async () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route index element={<LandingPage />} />
          <Route path="upload" element={<p>מסך ההעלאה</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole("img", { name: "משרד הבריאות" })).toBeTruthy();

    await userEvent.setup().click(screen.getByRole("link", { name: /התחלה: העלאת טפסים/ }));

    expect(screen.getByText("מסך ההעלאה")).toBeTruthy();
  });
});
