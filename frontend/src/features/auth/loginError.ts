// The message the login screen shows for each failure (PLAN-DEV-B 3.5).
// Owner: B

import { ApiError } from "../../api/client";
import { t } from "../../i18n";

/** What to tell the user. The server's own Hebrew title where it has one. */
export function loginError(failure: unknown): string {
  if (!(failure instanceof ApiError)) return t("common.failed");
  switch (failure.type) {
    case "invalid_credentials":
      return t("auth.errors.credentials");
    case "too_many_attempts":
      return t("auth.errors.tooMany");
    case "database_unavailable":
      return t("auth.errors.unavailable");
    default:
      return failure.message;
  }
}
