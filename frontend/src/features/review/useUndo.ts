// "Undo" for approve and delete. The server can't take either back, so the action
// waits UNDO_MS before it is sent, and "ביטול" drops it. One waits at a time: a new
// one sends the one before at once. Leaving the page sends it too, never drops it.
// Owner: B

import { useCallback, useEffect, useRef, useState } from "react";
import type { Saved } from "./recordMutations";

export const UNDO_MS = 5000;

export interface Undoable {
  /** What the toast says, e.g. "הרשומה של דנה לוי אושרה". */
  text: string;
  /** Sends it. null when done, else the message to show. */
  run: () => Promise<Saved>;
  /** Called on "ביטול", before anything was sent. */
  onUndo?: () => void;
  /** Called when the server refused it. */
  onFail?: (message: string) => void;
}

export function useUndo() {
  const [waiting, setWaiting] = useState<Undoable | null>(null);
  const [error, setError] = useState<string | null>(null);
  const current = useRef<Undoable | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const send = useCallback(() => {
    const action = current.current;
    clearTimeout(timer.current);
    current.current = null;
    setWaiting(null);
    if (!action) return;
    void action.run().then((message) => {
      if (message === null) return;
      setError(message);
      action.onFail?.(message);
    });
  }, []);

  const schedule = useCallback(
    (action: Undoable) => {
      send(); // the one before goes now
      setError(null);
      current.current = action;
      setWaiting(action);
      timer.current = setTimeout(send, UNDO_MS);
    },
    [send],
  );

  const undo = useCallback(() => {
    const action = current.current;
    clearTimeout(timer.current);
    current.current = null;
    setWaiting(null);
    action?.onUndo?.();
  }, []);

  // Closing the tab or leaving the screen sends what waits.
  useEffect(() => {
    window.addEventListener("pagehide", send);
    return () => {
      window.removeEventListener("pagehide", send);
      send();
    };
  }, [send]);

  return { waiting, error, schedule, undo, send, dismissError: () => setError(null) };
}
