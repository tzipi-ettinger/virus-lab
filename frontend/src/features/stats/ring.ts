// The records' status ring on the overview screen, as a CSS conic gradient.
// Owner: B

export interface RingPart {
  value: number;
  color: string;
}

/** The parts clockwise from the top, a thin gap between two; an empty part takes no room. */
export function ringGradient(parts: RingPart[]): string {
  const total = parts.reduce((sum, p) => sum + p.value, 0);
  const shown = parts.filter((p) => p.value > 0);
  const gap = shown.length > 1 ? 0.7 : 0;
  let start = 0;
  const stops = shown.map((p) => {
    const end = start + (p.value / total) * 100;
    const stop = `${p.color} ${start}% ${end - gap}%, var(--color-surface, #fff) 0 ${end}%`;
    start = end;
    return stop;
  });
  return `conic-gradient(${stops.join(", ")})`;
}
