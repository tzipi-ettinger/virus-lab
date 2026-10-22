// The overview screen: how many records wait for approval, the share of their fields
// still flagged, and which fields were corrected by hand the most (from the records'
// history). Over every record, with no filters.
// Owner: B

import { Link } from "react-router";
import { Skeleton } from "../../shared/ui/Skeleton";
import { fieldTitle } from "./fieldTitle";
import { useStats, type RecordStats } from "./useStats";
import "./StatsPage.css";

const percent = new Intl.NumberFormat("he-IL", { style: "percent", maximumFractionDigits: 1 });

function share(part: number, whole: number): number {
  return whole === 0 ? 0 : part / whole;
}

export function StatsPage() {
  const { state, reload } = useStats();
  return (
    <section className="stats" aria-labelledby="stats-title" aria-busy={state.status === "loading"}>
      <div className="stats-head">
        <h1 id="stats-title" className="stats-title">
          תמונת מצב
        </h1>
        <p className="stats-lead">כמה עבודה נשארה, ואיפה הקריאה האוטומטית צריכה הכי הרבה עזרה.</p>
      </div>
      {state.status === "loading" && (
        <div className="stats-card">
          <Skeleton rows={6} label="טוען נתונים…" />
        </div>
      )}
      {state.status === "error" && (
        <div className="stats-banner" role="alert">
          ⚠ {state.message}
          <button type="button" onClick={reload}>
            נסי שוב
          </button>
        </div>
      )}
      {state.status === "ready" && state.stats.pending + state.stats.approved === 0 && (
        <div className="stats-empty">
          <p>עוד אין רשומות, ולכן אין מה לסכם.</p>
          <Link to="/upload">להעלאת טפסים</Link>
        </div>
      )}
      {state.status === "ready" && state.stats.pending + state.stats.approved > 0 && (
        <Overview stats={state.stats} />
      )}
    </section>
  );
}

function Overview({ stats }: { stats: RecordStats }) {
  const ready = stats.pending - stats.needs_review;
  const flagged = share(stats.fields_flagged, stats.fields_total);
  const top = stats.by_field[0];
  return (
    <>
      <div className="stats-tiles">
        <section className="stats-card stats-tile" aria-labelledby="stats-pending">
          <h2 id="stats-pending" className="stats-tile-title">
            ממתינות לאישור
          </h2>
          <p className="stats-number">{stats.pending}</p>
          <p className="stats-note">
            {stats.needs_review > 0 && (
              <span className="stats-chip">
                <span aria-hidden="true">⚠</span> {stats.needs_review} דורשות בדיקה
              </span>
            )}
            {ready} מוכנות לאישור
          </p>
          {stats.pending > 0 && (
            <Link className="stats-link" to="/records?status=pending">
              לרשימת הממתינות ←
            </Link>
          )}
        </section>

        <section className="stats-card stats-tile" aria-labelledby="stats-flagged">
          <h2 id="stats-flagged" className="stats-tile-title">
            שדות שסומנו לבדיקה
          </h2>
          <p className="stats-number">
            <bdi>{percent.format(flagged)}</bdi>
          </p>
          <div className="stats-meter" aria-hidden="true">
            <span style={{ inlineSize: `${flagged * 100}%` }} />
          </div>
          <p className="stats-note">
            {stats.fields_flagged} מתוך {stats.fields_total} שדות ברשומות שעוד לא אושרו
          </p>
        </section>

        <section className="stats-card stats-tile" aria-labelledby="stats-corrections">
          <h2 id="stats-corrections" className="stats-tile-title">
            תיקונים ידניים
          </h2>
          <p className="stats-number">{stats.corrections}</p>
          <p className="stats-note">
            {stats.corrections === 0 ? (
              "עוד לא תוקן אף שדה"
            ) : (
              <>
                ב־{stats.corrected_records} רשומות. השדה שתוקן הכי הרבה: <strong>{fieldTitle(top.field)}</strong>
              </>
            )}
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
      <h2 id="stats-chart-title" className="stats-card-title">
        השדות שתוקנו הכי הרבה
      </h2>
      <p className="stats-card-lead">כמה פעמים כל שדה תוקן ביד, בכל הרשומות</p>
      {stats.by_field.length === 0 ? (
        <p className="stats-chart-empty">עוד לא תוקנו שדות. התיקונים יופיעו כאן אחרי העריכה הראשונה.</p>
      ) : (
        <ol className="stats-bars">
          {stats.by_field.map((f) => (
            <li key={f.field} title={`${fieldTitle(f.field)}: ${f.corrections} תיקונים`}>
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
  const parts = [
    { key: "approved", label: "✓ מאושרות", value: stats.approved },
    { key: "ready", label: "מוכנות לאישור", value: ready },
    { key: "review", label: "⚠ דורשות בדיקה", value: stats.needs_review },
  ];
  return (
    <section className="stats-card stats-status" aria-labelledby="stats-status-title">
      <h2 id="stats-status-title" className="stats-card-title">
        מצב כל הרשומות
      </h2>
      <p className="stats-card-lead">{total} רשומות במערכת</p>
      <div
        className="stats-stack"
        role="img"
        aria-label={`${stats.approved} מאושרות, ${ready} מוכנות לאישור, ${stats.needs_review} דורשות בדיקה`}
      >
        {parts
          .filter((p) => p.value > 0)
          .map((p) => (
            <span key={p.key} className={`is-${p.key}`} style={{ flexGrow: p.value }} />
          ))}
      </div>
      <ul className="stats-legend">
        {parts.map((p) => (
          <li key={p.key}>
            <span className={`stats-swatch is-${p.key}`} aria-hidden="true" />
            <span className="stats-legend-label">{p.label}</span>
            <strong>{p.value}</strong>
          </li>
        ))}
      </ul>
      <p className="stats-status-note">
        <strong>
          <bdi>{percent.format(share(stats.approved, total))}</bdi> כבר אושרו.
        </strong>{" "}
        רשומה עוברת לאישור רק כשאין בה שדה מסומן.
      </p>
    </section>
  );
}
