// The browser tab names the screen, then the site (WCAG 2.4.2): a screen reader
// reads it when the screen opens, and it tells open tabs apart. Never a patient's
// name or number: titles stay in the browser's history.
// Owner: shared

import { useEffect } from "react";

export const SITE_TITLE = "המעבדה המרכזית לנגיפים";

export function usePageTitle(screen: string) {
  useEffect(() => {
    document.title = `${screen} · ${SITE_TITLE}`;
  }, [screen]);
}
