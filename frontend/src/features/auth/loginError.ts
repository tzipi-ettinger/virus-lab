// The message the login screen shows for each failure (PLAN-DEV-B 3.5).
// Owner: B

import { ApiError } from "../../api/client";

/** What to tell the user. The server's own Hebrew title where it has one. */
export function loginError(failure: unknown): string {
  if (!(failure instanceof ApiError)) return "משהו השתבש. נסי שוב";
  switch (failure.type) {
    case "invalid_credentials":
      return "שם המשתמש או הסיסמה שגויים";
    case "too_many_attempts":
      return "יותר מדי ניסיונות. נסי שוב בעוד 15 דקות";
    case "database_unavailable":
      return "השרת לא זמין כרגע. נסי שוב בעוד דקה";
    default:
      return failure.message;
  }
}
