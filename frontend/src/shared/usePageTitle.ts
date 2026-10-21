// The browser tab names the screen that is open (WCAG 2.4.2): "<screen> · virus-lab".
// Owner: B

import { useEffect } from "react";

export function pageTitle(screen: string): string {
  return `${screen} · virus-lab`;
}

export function usePageTitle(screen: string) {
  useEffect(() => {
    document.title = pageTitle(screen);
  }, [screen]);
}
