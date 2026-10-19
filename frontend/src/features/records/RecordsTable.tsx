// The records list: one row per record, effective values only. A row opens its
// record page; the filters stay in the URL for the way back.
// Owner: B

import { Link, useLocation, useNavigate } from "react-router";
import type { components } from "../../api/schema";
import { FORM_TYPE_TEXT } from "../review/reviewRows";
import { formatDate, statusView } from "./format";

type RecordSummary = components["schemas"]["RecordSummary"];

export type BackTo = { back?: string };

export function RecordsTable({ items }: { items: RecordSummary[] }) {
  const navigate = useNavigate();
  const { search } = useLocation();
  const back: BackTo = { back: `/records${search}` };

  return (
    <div className="records-scroll">
      <table className="records-table">
        <thead>
          <tr>
            <th scope="col">שם</th>
            <th scope="col">ת״ז</th>
            <th scope="col">מספר התחייבות</th>
            <th scope="col">מספרים מרכזיים</th>
            <th scope="col">גורם שולח</th>
            <th scope="col">סוג טופס</th>
            <th scope="col">תאריך קבלה</th>
            <th scope="col">סטטוס</th>
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
                <td className="records-number">
                  <bdi>{r.central_numbers.join(", ") || "—"}</bdi>
                </td>
                <td>{r.sender ?? "—"}</td>
                <td>{FORM_TYPE_TEXT[r.form_type]}</td>
                <td>{formatDate(r.received_date)}</td>
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
