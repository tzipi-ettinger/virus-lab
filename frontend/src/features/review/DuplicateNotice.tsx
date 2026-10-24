// "Already in the history" (A4): an earlier record has the same commitment number
// and the same central numbers. Names every earlier copy, when it was saved and by
// whom, with a link to it. Shown on the upload screen and on the record page.
// The title is short on purpose; the issue's full message still shows with the field.
// Owner: B

import { Link } from "react-router";
import { t } from "../../i18n";
import { tRich } from "../../i18n/rich";
import { formatDateTime } from "../records/format";
import type { ApiRecord } from "./recordMutations";
import "./DuplicateNotice.css";

interface DuplicateNoticeProps {
  record: ApiRecord;
  /** Open the earlier record in a new tab, so the upload screen keeps its list. */
  newTab?: boolean;
}

export function DuplicateNotice({ record, newTab = false }: DuplicateNoticeProps) {
  const issue = record.fields.commitment_number.issues.find((i) => i.code === "DUPLICATE_RECORD");
  if (!issue) return null;
  const earlier = issue.duplicate_of ?? []; // records saved before this feature have no list
  return (
    <section className="duplicate-notice" aria-label={t("review.duplicate.label")}>
      <p className="duplicate-notice-title">⚠ {t("review.duplicate.title")}</p>
      {earlier.length > 0 && (
        <ul className="duplicate-notice-list">
          {earlier.map((copy) => {
            const to = `/records/${encodeURIComponent(copy.record_id)}`;
            return (
              <li key={copy.record_id}>
                {tRich("review.duplicate.entered", {
                  date: formatDateTime(copy.created_at),
                  who: <bdi>{copy.created_by}</bdi>,
                })}
                {" · "}
                {newTab ? (
                  <a href={to} target="_blank" rel="noopener noreferrer">
                    {t("review.duplicate.openNewTab")}
                  </a>
                ) : (
                  <Link to={to}>{t("review.duplicate.open")}</Link>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
