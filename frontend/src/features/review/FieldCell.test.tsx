// @vitest-environment jsdom
// Editing a field in place in the review table (PLAN-DEV-B 3.1, 3.3).
// Owner: B

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { components } from "../../api/schema";
import { FieldCell } from "./FieldCell";
import type { FieldEdit, Saved } from "./recordMutations";
import { field, flagged } from "./testRecords";

type FormField = components["schemas"]["FormField"];

afterEach(cleanup);

function renderCell(f: FormField, onSave = vi.fn<(edit: FieldEdit) => Promise<Saved>>().mockResolvedValue(null), editable = true) {
  render(
    <table>
      <tbody>
        <tr>
          <FieldCell title="ת״ז" field={f} editable={editable} onSave={onSave} />
        </tr>
      </tbody>
    </table>,
  );
  return onSave;
}

const open = async (user = userEvent.setup()) => {
  await user.click(screen.getByRole("button", { name: /^ת״ז:/ }));
  return user;
};

describe("FieldCell", () => {
  test("shows the value and its confidence in text", () => {
    renderCell(field("011223344", flagged("011223344")));

    expect(screen.getByText("011223344")).toBeTruthy();
    expect(screen.getByText("לא בטוח – בדקי")).toBeTruthy();
  });

  test("Enter saves the new value", async () => {
    const onSave = renderCell(field("11223344"));
    const user = await open();

    const input = screen.getByRole("textbox", { name: "עריכת ת״ז" });
    expect(document.activeElement).toBe(input);
    await user.clear(input);
    await user.type(input, "011223344{Enter}");

    expect(onSave).toHaveBeenCalledExactlyOnceWith({ value: "011223344" });
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  test("Escape cancels without saving", async () => {
    const onSave = renderCell(field("11223344"));
    const user = await open();

    await user.type(screen.getByRole("textbox"), "9{Escape}");

    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("11223344")).toBeTruthy();
  });

  test("leaving the field saves too", async () => {
    const onSave = renderCell(field("דנה"));
    const user = await open();

    await user.type(screen.getByRole("textbox"), "ה");
    await user.tab();

    expect(onSave).toHaveBeenCalledExactlyOnceWith({ value: "דנהה" });
  });

  test("an unchanged value sends nothing", async () => {
    const onSave = renderCell(field("דנה"));
    const user = await open();

    await user.keyboard("{Enter}");

    expect(onSave).not.toHaveBeenCalled();
  });

  test("an empty value clears the field", async () => {
    const onSave = renderCell(field("דנה"));
    const user = await open();

    await user.clear(screen.getByRole("textbox"));
    await user.keyboard("{Enter}");

    expect(onSave).toHaveBeenCalledWith({ value: null });
  });

  test("a failed save keeps the typed text open and says why", async () => {
    const onSave = vi.fn<(edit: FieldEdit) => Promise<Saved>>().mockResolvedValue("הרשומה עודכנה בחלון אחר");
    renderCell(field("1"), onSave);
    const user = await open();

    await user.type(screen.getByRole("textbox"), "2{Enter}");

    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("12");
    expect(screen.getByRole("alert").textContent).toBe("הרשומה עודכנה בחלון אחר");
  });

  test("a flagged value can be confirmed as it is", async () => {
    const onSave = renderCell(field("1122", flagged("1122")));

    await userEvent.setup().click(screen.getByRole("button", { name: "אישור ערך: ת״ז" }));

    expect(onSave).toHaveBeenCalledExactlyOnceWith({ confirmed: true });
  });

  test("an empty flagged field can be confirmed too", () => {
    renderCell(field(null, { needs_review: true }));

    expect(screen.getByRole("button", { name: "אישור ערך: ת״ז" })).toBeTruthy();
  });

  test("a confirmed field says so, keeps its issue, and needs no confirming", () => {
    renderCell(
      field("1122", {
        confirmed: true,
        issues: [{ code: "ID_CHECKSUM_INVALID", severity: "warning", message: "מספר ת״ז לא תקין" }],
      }),
    );

    expect(screen.getByText("אושר ידנית")).toBeTruthy();
    expect(screen.getByRole("cell").getAttribute("title")).toBe("מספר ת״ז לא תקין");
    expect(screen.queryByRole("button", { name: /אישור ערך/ })).toBeNull();
  });

  test("a clean field has nothing to confirm", () => {
    renderCell(field("011223344"));

    expect(screen.queryByRole("button", { name: /אישור ערך/ })).toBeNull();
  });

  test("a closed list edits with a dropdown that saves on pick", async () => {
    const onSave = vi.fn<(edit: FieldEdit) => Promise<Saved>>().mockResolvedValue(null);
    render(
      <table>
        <tbody>
          <tr>
            <FieldCell
              title="גורם שולח"
              field={field("מכבי העמק", flagged("מכבי העמק", "גורם שולח לא מוכר"))}
              editable
              onSave={onSave}
              options={["כללית", "מכבי"]}
            />
          </tr>
        </tbody>
      </table>,
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /^גורם שולח:/ }));
    const select = screen.getByRole("combobox", { name: "עריכת גורם שולח" });
    // The text as read stays available, marked as not on the list.
    expect((select as HTMLSelectElement).value).toBe("מכבי העמק");
    expect(screen.getByRole("option", { name: /כפי שנקרא: מכבי העמק/ })).toBeTruthy();
    await user.selectOptions(select, "מכבי");

    expect(onSave).toHaveBeenCalledExactlyOnceWith({ value: "מכבי" });
  });

  test("an approved record can't be edited", () => {
    renderCell(field("011223344"), undefined, false);

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("011223344")).toBeTruthy();
  });

  test("with showIssues, the reason is text under the value and describes its buttons", () => {
    render(
      <table>
        <tbody>
          <tr>
            <FieldCell
              title="ת״ז"
              field={field("1122", flagged("1122", "מספר ת״ז לא תקין"))}
              editable
              onSave={vi.fn<(edit: FieldEdit) => Promise<Saved>>()}
              showIssues
            />
          </tr>
        </tbody>
      </table>,
    );

    const reason = screen.getByText("מספר ת״ז לא תקין");
    expect(screen.getByRole("cell").getAttribute("title")).toBeNull();
    expect(screen.getByRole("button", { name: /^ת״ז:/ }).getAttribute("aria-describedby")).toBe(reason.parentElement?.id);
    expect(screen.getByRole("button", { name: "אישור ערך: ת״ז" }).getAttribute("aria-describedby")).toBe(
      reason.parentElement?.id,
    );
  });
});
