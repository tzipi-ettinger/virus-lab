// The closed list of senders (SPEC 5.5) from GET /senders, once per screen. For
// the sender filter and the sender dropdown. Without it, both still work on text.
// Owner: B

import { useEffect, useState } from "react";
import { apiFetch } from "../api/client";

export function useSenders(): string[] {
  const [senders, setSenders] = useState<string[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch<unknown>("/api/v1/senders", { signal: controller.signal }).then(
      (names) => setSenders(Array.isArray(names) ? names.filter((n) => typeof n === "string") : []),
      () => {},
    );
    return () => controller.abort();
  }, []);
  return senders;
}
