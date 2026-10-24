// A field's name on the overview screen, as the review screen names it.
// Owner: B

import { t } from "../../i18n";
import { FIELD_COLUMNS } from "../review/reviewRows";

/** "national_id" → ת״ז; "central_numbers" → מספר מרכזי. */
export function fieldTitle(field: string): string {
  if (field === "central_numbers") return t("fields.centralNumber");
  return FIELD_COLUMNS.find((c) => c.name === field)?.title ?? field;
}
