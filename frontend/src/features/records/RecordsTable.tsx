// The records list: one row per record, effective values only. A row opens its
// record page; the filters stay in the URL for the way back. A column header sorts
// by it, and a second click turns the order around.
// Owner: B

import { Link, useLocation, useNavigate } from "react-router";
import type { components } from "../../api/schema";
import { FORM_TYPE_TEXT } from "../review/reviewRows";
import { nextSort, sortDirection, type RecordSort, type SortColumn } from "./filters";
import { formatDate, statusView } from "./format";

type RecordSummary = components["schemas"]["RecordSummary"];

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
                <td>
                  {/* A real link too, for the keyboard and for opening in a new tab. */}
                  <Link to={`/records/${r.record_id}`} state={back} onClick={(e) => e.stopPropagation()}>
                    <bdi>{name}</bdi>
                  </Link>
                </td>
                <td className="records-number">
                  <bdi>{r.national_id ?? "—"}</bdi>
                </td>
                <td className="records-number">
                  <bdi>{r.commitment_number ?? "—"}</bdi>
                </td>
                <td className="records-number records-centrals">
                  <bdi>{r.central_numbers.join(", ") || "—"}</bdi>
                </td>
                <td>{r.sender ?? "—"}</td>
                <td>{FORM_TYPE_TEXT[r.form_type]}</td>
                <td className="records-number">{formatDate(r.received_date)}</td>
                <td>
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
