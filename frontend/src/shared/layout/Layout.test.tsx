// @vitest-environment jsdom
// The frame of every screen: a new screen takes the focus to its content and names
// itself in the browser tab (WCAG 2.4.2, 2.4.3).
// Owner: B

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, test } from "vitest";
import { usePageTitle } from "../usePageTitle";
import { Layout } from "./Layout";

afterEach(cleanup);

function Screen({ name }: { name: string }) {
  usePageTitle(name);
  return (
    <>
      <Link to="/records">רשימה</Link>
      <Link to="/records?status=approved">מאושרות</Link>
    </>
  );
}

function renderApp() {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Screen name="העלאה ובדיקה" />} />
          <Route path="records" element={<Screen name="רשומות" />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

describe("Layout", () => {
  test("the first screen leaves the focus alone and names the tab", () => {
    renderApp();

    expect(document.activeElement).toBe(document.body);
    expect(document.title).toBe("העלאה ובדיקה · virus-lab");
  });

  test("a new screen moves the focus to its content and renames the tab", async () => {
    const user = renderApp();

    await user.click(screen.getByRole("link", { name: "רשימה" }));

    expect(document.activeElement).toBe(screen.getByRole("main"));
    expect(document.title).toBe("רשומות · virus-lab");
  });

  test("a filter change on the same screen keeps the focus where it is", async () => {
    const user = renderApp();
    await user.click(screen.getByRole("link", { name: "רשימה" }));

    const filter = screen.getByRole("link", { name: "מאושרות" });
    await user.click(filter);

    expect(document.activeElement).toBe(filter);
  });
});
