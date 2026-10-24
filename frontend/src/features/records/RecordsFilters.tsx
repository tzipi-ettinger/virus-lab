// Search and filters for the records screen (PLAN-DEV-B 3.1). Each control writes
// to the URL through onChange; the search waits 300ms after the last key.
// Owner: B

import { useEffect, useState } from "react";
import { t } from "../../i18n";
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
        {t("fields.status")}
        <select
          value={filters.status ?? ""}
          onChange={(e) => onChange({ status: (e.target.value || null) as RecordStatus | null })}
        >
          <option value="">{t("common.all")}</option>
          <option value="pending">{t("records.filters.pending")}</option>
          <option value="approved">{t("records.filters.approved")}</option>
        </select>
      </label>
      <label className="records-filter-sender">
        {t("fields.sender")}
        <select value={filters.sender} onChange={(e) => onChange({ sender: e.target.value })}>
          <option value="">{t("common.all")}</option>
          {senderOptions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <label className="records-filter-form">
        {t("fields.form_type")}
        <select
          value={filters.formType ?? ""}
          onChange={(e) => onChange({ formType: (e.target.value || null) as FormType | null })}
        >
          <option value="">{t("common.all")}</option>
          {(Object.entries(FORM_TYPE_TEXT) as [FormType, string][]).map(([value, text]) => (
            <option key={value} value={value}>
              {text}
            </option>
          ))}
        </select>
      </label>
      {/* One range field, so the two dates never end up on different rows. */}
      <fieldset className="records-dates">
        <legend>{t("fields.received_date")}</legend>
        <div className="records-dates-inputs">
          <input
            type="date"
            aria-label={t("records.filters.dateFrom")}
            value={filters.dateFrom}
            onChange={(e) => onChange({ dateFrom: e.target.value })}
          />
          <span aria-hidden="true">–</span>
          <input
            type="date"
            aria-label={t("records.filters.dateTo")}
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
      {t("records.filters.search")}
      <span className="records-search-box">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M20 20l-4-4M18 11a7 7 0 1 1-14 0 7 7 0 0 1 14 0" />
        </svg>
        <input
          type="search"
          placeholder={t("records.filters.searchHint")}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
      </span>
    </label>
  );
}
