// The records list: one row per record, effective values only. A row opens its
// record page; the filters stay in the URL for the way back. A column header sorts
// by it, and a second click turns the order around.
// Owner: B

import { Link, useLocation, useNavigate } from "react-router";
import type { components } from "../../api/schema";
import { FORM_TYPE_TEXT } from "../review/reviewRows";
import { nextSort, sortDirection, type RecordSort, type SortColumn } from "./filters";
import { formatDate, senderTag, statusView } from "./format";

type RecordSummary = components["schemas"]["RecordSummary"];
type FormType = RecordSummary["form_type"];

// A small line icon beside each form type, so the column reads at a glance.
const FORM_ICONS: Record<FormType, string> = {
  hospital_form: "M4 21V5l8-3 8 3v16M12 8v6M9 11h6M2 21h20",
  hmo_form: "M3 21h18M5 21V9l7-5 7 5v12M10 21v-5h4v5",
  hospital_system_screenshot: "M3 4h18v12H3zM8 20h8M12 16v4",
  lab_report: "M9 3h6M10 3v6l-5.5 10a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3",
  private_lab: "M9 3h6M10 3v6l-5.5 10a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3",
  government: "M3 21h18M5 21V10M19 21V10M9.5 21V10M14.5 21V10M2 10l10-6 10 6",
  unknown: "M6 2h9l5 5v15H6zM10 10a2 2 0 1 1 3 1.7c-.6.4-1 1-1 1.8M12 17h.01",
};

export type BackTo = { back?: string };

interface Props {
  items: RecordSummary[];
  sort: RecordSort;
  onSort: (sort: RecordSort) => void;
}

// The name column sorts by last name, as the lab files people.
const COLUMNS: { title: string; sort: SortColumn | null }[] = [
  { title: "שם", sort: "last_name" },
  { title: "ת״ז", sort: "national_id" },
  { title: "מספר התחייבות", sort: "commitment_number" },
  { title: "מספרים מרכזיים", sort: null }, // a list: no single value to sort by
  { title: "גורם שולח", sort: "sender" },
  { title: "סוג טופס", sort: "form_type" },
  { title: "תאריך קבלה", sort: "received_date" },
  { title: "סטטוס", sort: "status" },
];

const ARROW = { ascending: "▲", descending: "▼", none: "" };

// Each cell carries its column's title: on a narrow screen a row turns into a
// card, and the title shows above the value.
const [NAME, ID, COMMITMENT, CENTRALS, SENDER, FORM, DATE, STATUS] = COLUMNS.map((c) => c.title);

export function RecordsTable({ items, sort, onSort }: Props) {
  const navigate = useNavigate();
  const { search } = useLocation();
  const back: BackTo = { back: `/records${search}` };

  return (
    <div className="records-scroll">
      <table className="records-table">
        <thead>
          <tr>
            {COLUMNS.map(({ title, sort: column }) => {
              if (column === null) {
                return (
                  <th key={title} scope="col">
                    {title}
                  </th>
                );
              }
              const direction = sortDirection(sort, column);
              return (
                <th key={title} scope="col" aria-sort={direction}>
                  <button type="button" className="records-sort" onClick={() => onSort(nextSort(sort, column))}>
                    {title}
                    <span aria-hidden="true" className="records-sort-arrow">
                      {ARROW[direction]}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {items.map((r) => {
            const status = statusView(r);
            const name = [r.first_name, r.last_name].filter(Boolean).join(" ") || "ללא שם";
            return (
              <tr key={r.record_id} onClick={() => navigate(`/records/${r.record_id}`, { state: back })}>
                <td data-label={NAME}>
                  {/* A real link too, for the keyboard and for opening in a new tab. */}
                  <Link to={`/records/${r.record_id}`} state={back} onClick={(e) => e.stopPropagation()}>
                    <bdi>{name}</bdi>
                  </Link>
                </td>
                <td className="records-number" data-label={ID}>
                  <bdi>{r.national_id ?? "—"}</bdi>
                </td>
                <td className="records-number" data-label={COMMITMENT}>
                  <bdi>{r.commitment_number ?? "—"}</bdi>
                </td>
                <td className="records-number records-centrals" data-label={CENTRALS}>
                  {r.central_numbers.length > 0 ? (
                    <bdi className="records-centrals-list">{r.central_numbers.join(", ")}</bdi>
                  ) : (
                    "—"
                  )}
                </td>
                <td data-label={SENDER}>
                  {r.sender ? <span className={`records-sender is-tag-${senderTag(r.sender)}`}>{r.sender}</span> : "—"}
                </td>
                <td data-label={FORM}>
                  <span className="records-form">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                      <path d={FORM_ICONS[r.form_type]} />
                    </svg>
                    {FORM_TYPE_TEXT[r.form_type]}
                  </span>
                </td>
                <td className="records-number" data-label={DATE}>{formatDate(r.received_date)}</td>
                <td data-label={STATUS}>
                  <span className={`records-status is-${status.tone}`}>
                    <span aria-hidden="true">{status.icon}</span> {status.text}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
