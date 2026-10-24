// Download the records the screen shows, as CSV or JSON (PLAN-DEV-B B1.9, D19).
// Plain links: the browser downloads the file and sends the session cookie itself.
// Owner: B

import { t } from "../../i18n";
import { exportUrl, type RecordFilters } from "./filters";

interface ExportButtonProps {
  filters: RecordFilters;
  total: number; // records that match the filters, on every page
}

export function ExportButton({ filters, total }: ExportButtonProps) {
  if (total === 0) {
    return (
      <div className="records-export">
        <span className="records-export-label">{t("records.export.empty")}</span>
        <span className="records-export-none">{t("records.export.nothing")}</span>
      </div>
    );
  }
  return (
    <div className="records-export" role="group" aria-label={t("records.export.label")}>
      <span className="records-export-label">{t("records.export.count", { n: total })}</span>
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
