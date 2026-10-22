// "Already in the history" (A4): an earlier record has the same commitment number
// and the same central numbers. Names every earlier copy, when it was saved and by
// whom, with a link to it. Shown on the upload screen and on the record page.
// Owner: B

import { Link } from "react-router";
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
    <section className="duplicate-notice" aria-label="כבר קיים בהיסטוריה">
      <p className="duplicate-notice-title">⚠ {issue.message}</p>
      {earlier.length > 0 && (
        <ul className="duplicate-notice-list">
          {earlier.map((copy) => {
            const to = `/records/${encodeURIComponent(copy.record_id)}`;
            return (
              <li key={copy.record_id}>
                הוכנס ב־{formatDateTime(copy.created_at)} על ידי <bdi>{copy.created_by}</bdi>
                {" · "}
                {newTab ? (
                  <a href={to} target="_blank" rel="noopener noreferrer">
                    פתיחת הרשומה (בכרטיסייה חדשה)
                  </a>
                ) : (
                  <Link to={to}>פתיחת הרשומה</Link>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
