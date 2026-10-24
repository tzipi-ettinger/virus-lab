// Gray bars that shimmer while a screen loads: the shape of what is coming instead
// of a bare "loading". The words stay, for screen readers.
// Owner: shared

import { t } from "../../i18n";
import "./Skeleton.css";

interface Props {
  rows?: number;
  label?: string;
}

export function Skeleton({ rows = 8, label = t("common.loading") }: Props) {
  return (
    <div className="skeleton" role="status">
      <span className="skeleton-label">{label}</span>
      <div className="skeleton-row is-head" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </div>
      ))}
    </div>
  );
}
