// How the records screens show dates and statuses. No React here.
// Owner: B

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** 2026-10-19 → 19/10/2026, the format the lab reads. Anything else as it is. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const match = ISO_DATE.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}

const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Jerusalem",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/** A server timestamp in Israel time: 19/10/2026 14:05. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : DATE_TIME.format(date).replace(",", "");
}

export interface StatusView {
  icon: string;
  text: string;
  tone: "approved" | "review" | "ready";
}

export const SENDER_TAGS = 6; // --color-tag-1 … --color-tag-6

/** A sender's tag color, 1 to SENDER_TAGS, from its name: the same on every row and visit. */
export function senderTag(name: string): number {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + (char.codePointAt(0) ?? 0)) % 100_003;
  return (hash % SENDER_TAGS) + 1;
}

/** Every status in text and an icon too, never by color alone (PLAN-DEV-B 3.0). */
export function statusView(record: { status: string; needs_review: boolean }): StatusView {
  if (record.status === "approved") return { icon: "✓", text: "אושר", tone: "approved" };
  if (record.needs_review) return { icon: "⚠", text: "דורש בדיקה", tone: "review" };
  return { icon: "○", text: "ממתין לאישור", tone: "ready" };
}
