// @vitest-environment jsdom
// Editing the central numbers list in the review table (PLAN-DEV-B 3.2).
// Owner: B

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { components } from "../../api/schema";
import { CentralNumbersCell } from "./CentralNumbersCell";
import type { ListItemEdit, Saved } from "./recordMutations";
import { field, flagged } from "./testRecords";

type FormField = components["schemas"]["FormField"];

afterEach(cleanup);

function renderCell(items: FormField[], editable = true) {
  const onSave = vi.fn<(items: ListItemEdit[]) => Promise<Saved>>().mockResolvedValue(null);
  render(
    <table>
      <tbody>
        <tr>
          <CentralNumbersCell items={items} editable={editable} onSave={onSave} />
        </tr>
      </tbody>
    </table>,
  );
  return onSave;
}

describe("CentralNumbersCell", () => {
  test("each number shows its own confidence", () => {
    renderCell([field("948062"), field("12345", flagged("12345", "מספר מרכזי בפורמט חריג"))]);

    expect(screen.getByText("948062")).toBeTruthy();
    expect(screen.getByText("בטוח")).toBeTruthy();
    expect(screen.getByText("לא בטוח – בדקי")).toBeTruthy();
  });

  test("a flagged number is confirmed alone, the others kept by position", async () => {
    const onSave = renderCell([field("948062"), field("12345", flagged("12345"))]);

    await userEvent.setup().click(screen.getByRole("button", { name: "אישור ערך: מספר מרכזי 2" }));

    expect(onSave).toHaveBeenCalledExactlyOnceWith([{ idx: 0 }, { idx: 1, confirmed: true }]);
  });

  test("edits, adds and removes numbers, and sends the full list", async () => {
    const onSave = renderCell([field("948062"), field("12345")]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "עריכת הרשימה" }));
    await user.clear(screen.getByRole("textbox", { name: "מספר מרכזי 2" }));
    await user.type(screen.getByRole("textbox", { name: "מספר מרכזי 2" }), "123456");
    await user.click(screen.getByRole("button", { name: "+ הוספה" }));
    await user.type(screen.getByRole("textbox", { name: "מספר מרכזי 3" }), "555555");
    await user.click(screen.getByRole("button", { name: "הסרת מספר מרכזי 1" }));
    await user.click(screen.getByRole("button", { name: "שמירה" }));

    expect(onSave).toHaveBeenCalledExactlyOnceWith([{ idx: 1, value: "123456" }, { value: "555555" }]);
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  test("cancel leaves the list as it was", async () => {
    const onSave = renderCell([field("948062")]);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "עריכת הרשימה" }));
    await user.type(screen.getByRole("textbox", { name: "מספר מרכזי 1" }), "9");
    await user.click(screen.getByRole("button", { name: "ביטול" }));

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("948062")).toBeTruthy();
  });

  test("an approved record can't be changed", () => {
    renderCell([field("948062", flagged("948062"))], false);

    expect(screen.queryByRole("button")).toBeNull();
  });

  test("with showIssues, each number's reason is text under it", () => {
    render(
      <table>
        <tbody>
          <tr>
            <CentralNumbersCell
              items={[field("948062"), field("12345", flagged("12345", "מספר מרכזי בפורמט חריג"))]}
              editable
              onSave={vi.fn<(items: ListItemEdit[]) => Promise<Saved>>()}
              showIssues
            />
          </tr>
        </tbody>
      </table>,
    );

    const [clean, odd] = screen.getAllByRole("listitem");
    expect(odd.textContent).toContain("מספר מרכזי בפורמט חריג");
    expect(clean.textContent).not.toContain("חריג");
    expect(screen.getByRole("cell").getAttribute("title")).toBeNull();
  });
});
