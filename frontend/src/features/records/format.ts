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

/** Every status in text and an icon too, never by color alone (PLAN-DEV-B 3.0). */
export function statusView(record: { status: string; needs_review: boolean }): StatusView {
  if (record.status === "approved") return { icon: "✓", text: "אושר", tone: "approved" };
  if (record.needs_review) return { icon: "⚠", text: "דורש בדיקה", tone: "review" };
  return { icon: "○", text: "ממתין לאישור", tone: "ready" };
}
