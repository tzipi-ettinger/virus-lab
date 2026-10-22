// A field's name on the overview screen, as the review screen names it.
// Owner: B

import { FIELD_COLUMNS } from "../review/reviewRows";

/** "national_id" → ת״ז; "central_numbers" → מספר מרכזי. */
export function fieldTitle(field: string): string {
  if (field === "central_numbers") return "מספר מרכזי";
  return FIELD_COLUMNS.find((c) => c.name === field)?.title ?? field;
}
