// A greeting for the time of day, on the login screen.
// Owner: B

/** "Good morning" and so on, by the hour on the user's clock (0-23). */
export function greeting(hour: number): string {
  if (hour >= 5 && hour < 12) return "בוקר טוב";
  if (hour >= 12 && hour < 17) return "צהריים טובים";
  if (hour >= 17 && hour < 22) return "ערב טוב";
  return "לילה טוב";
}
