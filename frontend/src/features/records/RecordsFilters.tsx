// Search and filters for the records screen (PLAN-DEV-B 3.1). Each control writes
// to the URL through onChange; the search waits 300ms after the last key.
// Owner: B

import { useEffect, useState } from "react";
import { useSenders } from "../../shared/useSenders";
import { FORM_TYPE_TEXT } from "../review/reviewRows";
import type { FormType, RecordFilters, RecordStatus } from "./filters";

export const SEARCH_DELAY_MS = 300;

interface Props {
  filters: RecordFilters;
  onChange: (change: Partial<RecordFilters>) => void;
}

export function RecordsFilters({ filters, onChange }: Props) {
  const senders = useSenders();
  // A sender in the URL that isn't on the list (an old link) still shows.
  const senderOptions =
    filters.sender && !senders.includes(filters.sender) ? [filters.sender, ...senders] : senders;

  return (
    <form className="records-filters" role="search" onSubmit={(event) => event.preventDefault()}>
      <SearchBox value={filters.q} onSearch={(q) => onChange({ q })} />
      <label className="records-filter-status">
        סטטוס
        <select
          value={filters.status ?? ""}
          onChange={(e) => onChange({ status: (e.target.value || null) as RecordStatus | null })}
        >
          <option value="">הכול</option>
          <option value="pending">ממתין</option>
          <option value="approved">מאושר</option>
        </select>
      </label>
      <label className="records-check">
        <input
          type="checkbox"
          checked={filters.needsReview}
          onChange={(e) => onChange({ needsReview: e.target.checked })}
        />
        רק דורשות בדיקה
      </label>
      <label className="records-filter-sender">
        גורם שולח
        <select value={filters.sender} onChange={(e) => onChange({ sender: e.target.value })}>
          <option value="">הכול</option>
          {senderOptions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label className="records-filter-form">
        סוג טופס
        <select
          value={filters.formType ?? ""}
          onChange={(e) => onChange({ formType: (e.target.value || null) as FormType | null })}
        >
          <option value="">הכול</option>
          {(Object.entries(FORM_TYPE_TEXT) as [FormType, string][]).map(([value, text]) => (
            <option key={value} value={value}>
              {text}
            </option>
          ))}
        </select>
      </label>
      {/* One range field, so the two dates never end up on different rows. */}
      <fieldset className="records-dates">
        <legend>תאריך קבלה</legend>
        <div className="records-dates-inputs">
          <input
            type="date"
            aria-label="מתאריך קבלה"
            value={filters.dateFrom}
            onChange={(e) => onChange({ dateFrom: e.target.value })}
          />
          <span aria-hidden="true">–</span>
          <input
            type="date"
            aria-label="עד תאריך קבלה"
            value={filters.dateTo}
            onChange={(e) => onChange({ dateTo: e.target.value })}
          />
        </div>
      </fieldset>
    </form>
  );
}

function SearchBox({ value, onSearch }: { value: string; onSearch: (q: string) => void }) {
  const [draft, setDraft] = useState(value);
  const [synced, setSynced] = useState(value);
  // The URL changed from elsewhere (clear filters, back button): show that.
  if (value !== synced) {
    setSynced(value);
    setDraft(value);
  }

  useEffect(() => {
    if (draft.trim() === value) return;
    const timer = setTimeout(() => onSearch(draft.trim()), SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [draft, value, onSearch]);

  return (
    <label className="records-search">
      חיפוש
      <input
        type="search"
        placeholder="שם, ת״ז, מספר מרכזי או התחייבות"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
      />
    </label>
  );
}
