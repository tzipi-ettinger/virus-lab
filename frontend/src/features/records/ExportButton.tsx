// Download the records the screen shows, as CSV or JSON (PLAN-DEV-B B1.9, D19).
// Plain links: the browser downloads the file and sends the session cookie itself.
// Owner: B

import { exportUrl, type RecordFilters } from "./filters";

interface ExportButtonProps {
  filters: RecordFilters;
  total: number; // records that match the filters, on every page
}

export function ExportButton({ filters, total }: ExportButtonProps) {
  if (total === 0) {
    return (
      <div className="records-export">
        <span className="records-export-label">ייצוא:</span>
        <span className="records-export-none">אין רשומות לייצוא לפי הסינון הנוכחי</span>
      </div>
    );
  }
  return (
    <div className="records-export" role="group" aria-label="ייצוא">
      <span className="records-export-label">ייצוא {total} רשומות:</span>
      <a href={exportUrl(filters, "csv")} download>
        CSV
      </a>
      <a href={exportUrl(filters, "json")} download>
        JSON
      </a>
    </div>
  );
}

export default ExportButton;
