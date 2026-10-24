// The overview screen: how many records wait for approval, the share of their fields
// still flagged, and which fields were corrected by hand the most (from the records'
// history). Over every record, with no filters.
// Owner: B

import { Link } from "react-router";
import { t } from "../../i18n";
import { tRich } from "../../i18n/rich";
import { Skeleton } from "../../shared/ui/Skeleton";
import { fieldTitle } from "./fieldTitle";
import { ringGradient } from "./ring";
import { useStats, type RecordStats } from "./useStats";
import "./StatsPage.css";

const percent = new Intl.NumberFormat("he-IL", { style: "percent", maximumFractionDigits: 1 });

function share(part: number, whole: number): number {
  return whole === 0 ? 0 : part / whole;
}

// Line icons, drawn like the navigation's.
const ICONS = {
  clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  flag: "M5 21V4h12l-2.5 4L17 12H5",
  pencil: "M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4",
  bars: "M20 6H8M20 12H4M20 18h-9",
  ring: "M12 3v9h9M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  check: "M5 12l5 5 9-10",
  ready: "M9 12l2 2 4-4M20 12a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  warning: "M12 3 2 20h20L12 3zM12 10v4M12 17h.01",
  info: "M12 11v5M12 8h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
};

function Icon({ name, size = 20 }: { name: keyof typeof ICONS; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name]} />
    </svg>
  );
}

export function StatsPage() {
  const { state, reload } = useStats();
  const total = state.status === "ready" ? state.stats.pending + state.stats.approved : 0;
  return (
    <section className="stats" aria-labelledby="stats-title" aria-busy={state.status === "loading"}>
      <div className="stats-head">
        <h1 id="stats-title" className="stats-title">
          {t("stats.title")}
        </h1>
        <p className="stats-lead">{t("stats.lead")}</p>
        {total > 0 && <p className="stats-total">{t("stats.total", { n: total })}</p>}
      </div>
      {state.status === "loading" && (
        <div className="stats-card">
          <Skeleton rows={6} label={t("stats.loading")} />
        </div>
      )}
      {state.status === "error" && (
        <div className="stats-banner" role="alert">
          ⚠ {state.message}
          <button type="button" onClick={reload}>
            {t("common.retry")}
          </button>
        </div>
      )}
      {state.status === "ready" && total === 0 && (
        <div className="stats-empty">
          <p>{t("stats.empty")}</p>
          <Link to="/upload">{t("stats.toUpload")}</Link>
        </div>
      )}
      {state.status === "ready" && total > 0 && <Overview stats={state.stats} />}
    </section>
  );
}

function Overview({ stats }: { stats: RecordStats }) {
  const ready = stats.pending - stats.needs_review;
  const flagged = share(stats.fields_flagged, stats.fields_total);
  const top = stats.by_field[0];
  return (
    <>
      {/* Each tile in a hue of its own, kept by its card below: blue for what waits,
          amber for what is flagged, violet for the corrections. */}
      <div className="stats-tiles">
        <section className="stats-card stats-tile is-pending" aria-labelledby="stats-pending">
          <div className="stats-tile-head">
            <span className="stats-tile-icon">
              <Icon name="clock" />
            </span>
            <h2 id="stats-pending" className="stats-tile-title">
              {t("stats.pending.title")}
            </h2>
          </div>
          <p className="stats-number">{stats.pending}</p>
          <p className="stats-note">
            {stats.needs_review > 0 && (
              <span className="stats-chip is-review">
                <Icon name="warning" size={15} /> {t("stats.pending.review", { n: stats.needs_review })}
              </span>
            )}
            <span className="stats-chip is-ready">{t("stats.pending.ready", { n: ready })}</span>
          </p>
          {stats.pending > 0 && (
            <Link className="stats-link" to="/records?status=pending">
              {t("stats.pending.link")}
            </Link>
          )}
        </section>

        <section className="stats-card stats-tile is-flagged" aria-labelledby="stats-flagged">
          <div className="stats-tile-head">
            <span className="stats-tile-icon">
              <Icon name="flag" />
            </span>
            <h2 id="stats-flagged" className="stats-tile-title">
              {t("stats.flagged.title")}
            </h2>
          </div>
          <p className="stats-number">
            <bdi>{percent.format(flagged)}</bdi>
          </p>
          <div className="stats-meter" aria-hidden="true">
            <span style={{ inlineSize: `${flagged * 100}%` }} />
          </div>
          <p className="stats-note">
            {t("stats.flagged.note", { flagged: stats.fields_flagged, total: stats.fields_total })}
          </p>
        </section>

        <section className="stats-card stats-tile is-fixed" aria-labelledby="stats-corrections">
          <div className="stats-tile-head">
            <span className="stats-tile-icon">
              <Icon name="pencil" />
            </span>
            <h2 id="stats-corrections" className="stats-tile-title">
              {t("stats.fixed.title")}
            </h2>
          </div>
          <p className="stats-number">{stats.corrections}</p>
          <p className="stats-note">
            {stats.corrections === 0
              ? t("stats.fixed.none")
              : tRich("stats.fixed.note", {
                  n: stats.corrected_records,
                  field: <strong>{fieldTitle(top.field)}</strong>,
                })}
          </p>
        </section>
      </div>

      <div className="stats-row">
        <CorrectionsChart stats={stats} />
        <StatusCard stats={stats} />
      </div>
    </>
  );
}

function CorrectionsChart({ stats }: { stats: RecordStats }) {
  const max = Math.max(1, ...stats.by_field.map((f) => f.corrections));
  return (
    <section className="stats-card stats-chart" aria-labelledby="stats-chart-title">
      <div className="stats-card-head">
        <span className="stats-card-icon">
          <Icon name="bars" />
        </span>
        <div>
          <h2 id="stats-chart-title" className="stats-card-title">
            {t("stats.chart.title")}
          </h2>
          <p className="stats-card-lead">{t("stats.chart.lead")}</p>
        </div>
      </div>
      {stats.by_field.length === 0 ? (
        <div className="stats-chart-empty">
          <span className="stats-chart-empty-icon">
            <Icon name="pencil" size={30} />
          </span>
          <p className="stats-chart-empty-title">{t("stats.chart.emptyTitle")}</p>
          <p>{t("stats.chart.emptyText")}</p>
        </div>
      ) : (
        <ol className="stats-bars">
          {stats.by_field.map((f) => (
            <li key={f.field} title={t("stats.chart.bar", { field: fieldTitle(f.field), n: f.corrections })}>
              <span className="stats-bar-label">{fieldTitle(f.field)}</span>
              <span className="stats-bar-track">
                <span className="stats-bar" style={{ inlineSize: `${(f.corrections / max) * 88}%` }} />
                <span className="stats-bar-value">{f.corrections}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function StatusCard({ stats }: { stats: RecordStats }) {
  const total = stats.pending + stats.approved;
  const ready = stats.pending - stats.needs_review;
  const approved = <bdi>{percent.format(share(stats.approved, total))}</bdi>;
  const parts = [
    { key: "approved", icon: "check", value: stats.approved, color: "var(--color-success-fill, #2f9e5b)" },
    { key: "ready", icon: "ready", value: ready, color: "var(--color-accent, #1f6fb2)" },
    { key: "review", icon: "warning", value: stats.needs_review, color: "var(--color-warning-fill, #f0b429)" },
  ] as const;
  return (
    <section className="stats-card stats-status" aria-labelledby="stats-status-title">
      <div className="stats-card-head">
        <span className="stats-card-icon">
          <Icon name="ring" />
        </span>
        <div>
          <h2 id="stats-status-title" className="stats-card-title">
            {t("stats.status.title")}
          </h2>
          <p className="stats-card-lead">{t("stats.total", { n: total })}</p>
        </div>
      </div>
      <div className="stats-status-body">
        <div
          className="stats-ring"
          role="img"
          aria-label={t("stats.status.ring", { approved: stats.approved, ready, review: stats.needs_review })}
          style={{ background: ringGradient([...parts]) }}
        >
          <span className="stats-ring-hole">
            <strong>{approved}</strong>
            {t("stats.status.approvedShort")}
          </span>
        </div>
        <ul className="stats-legend">
          {parts.map((p) => (
            <li key={p.key} className={`is-${p.key}`}>
              <span className="stats-swatch" aria-hidden="true" />
              <span className="stats-legend-label">
                <Icon name={p.icon} size={15} />
                {t(`stats.status.${p.key}`)}
              </span>
              <strong>{p.value}</strong>
            </li>
          ))}
        </ul>
      </div>
      <p className="stats-status-note">
        <Icon name="info" size={18} />
        <span>
          {tRich("stats.status.note", {
            approved: <strong>{tRich("stats.status.approvedShare", { pct: approved })}</strong>,
          })}
        </span>
      </p>
    </section>
  );
}
