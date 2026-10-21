// Which field row is boxed on the original page (field boxes). Keyboard focus boxes a
// row at once; the pointer only once it rests on the row, so moving the mouse down
// the table to "approve" doesn't flip the preview through every field's page.
// Owner: A

import { useEffect, useRef, useState } from "react";

export const HOVER_DELAY_MS = 150;
// Long enough to cross from the table to the preview without losing the box.
export const LEAVE_DELAY_MS = 300;

/**
 * `scope` is the record: a row picked on one record is not boxed on the next.
 * Spread `rowProps(name)` on each row, and `areaProps` on the table and on the
 * preview: once the pointer is out of both, the box goes. `focused` is the boxed
 * row's name, or null.
 */
export function useFieldFocus<Name>(scope: string) {
  const [focus, setFocus] = useState<{ scope: string; name: Name } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const leave = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(
    () => () => {
      clearTimeout(timer.current);
      clearTimeout(leave.current);
    },
    [],
  );

  function rowProps(name: Name) {
    return {
      onMouseEnter: () => {
        clearTimeout(timer.current);
        timer.current = setTimeout(() => setFocus({ scope, name }), HOVER_DELAY_MS);
      },
      onMouseLeave: () => clearTimeout(timer.current),
      onFocus: () => {
        clearTimeout(timer.current);
        setFocus({ scope, name });
      },
    };
  }

  const areaProps = {
    onMouseEnter: () => clearTimeout(leave.current),
    onMouseLeave: () => {
      clearTimeout(timer.current);
      clearTimeout(leave.current);
      leave.current = setTimeout(() => setFocus(null), LEAVE_DELAY_MS);
    },
  };

  return { focused: focus?.scope === scope ? focus.name : null, rowProps, areaProps };
}
