// A text with an element inside it: {file} as <bdi>, {field} as <strong>. The
// sentence stays whole in he.json, in its own word order, not cut around the element.
// Owner: B

import { Fragment, createElement, type ReactNode } from "react";
import { t, type TextKey } from "./index";

/** Like t, but a value may be an element. */
export function tRich(key: TextKey, values: Record<string, ReactNode>): ReactNode {
  const parts = t(key)
    .split(/(\{\w+\})/)
    .filter(Boolean)
    .map((part) => {
      const name = /^\{(\w+)\}$/.exec(part)?.[1];
      return name !== undefined && name in values ? values[name] : part;
    });
  return createElement(Fragment, null, ...parts);
}
