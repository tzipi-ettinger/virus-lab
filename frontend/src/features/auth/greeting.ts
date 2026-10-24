// A greeting for the time of day, on the login screen.
// Owner: B

import { t } from "../../i18n";

/** "Good morning" and so on, by the hour on the user's clock (0-23). */
export function greeting(hour: number): string {
  if (hour >= 5 && hour < 12) return t("auth.greeting.morning");
  if (hour >= 12 && hour < 17) return t("auth.greeting.noon");
  if (hour >= 17 && hour < 22) return t("auth.greeting.evening");
  return t("auth.greeting.night");
}
