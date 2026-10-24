// The landing page: the ministry's logo, what the system does in three steps, and
// the way in to the upload. No data, no calls to the server.
// Owner: shared

import { Link } from "react-router";
import { t } from "../../i18n";
import { LanguageSwitch } from "../../shared/ui/LanguageSwitch";
import "./LandingPage.css";

const STEPS = [
  {
    title: t("landing.uploadTitle"),
    text: t("landing.uploadText"),
    icon: (
      <>
        <path d="M12 16V4" />
        <path d="m6 10 6-6 6 6" />
        <path d="M4 20h16" />
      </>
    ),
  },
  {
    title: t("landing.readTitle"),
    text: t("landing.readText"),
    icon: (
      <>
        <rect x="4" y="3" width="16" height="18" rx="2" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </>
    ),
  },
  {
    title: t("landing.reviewTitle"),
    text: t("landing.reviewText"),
    icon: <path d="M5 12.5 10 17l9-10" />,
  },
];

export function LandingPage() {
  return (
    <div className="landing">
      <div className="landing-glow" aria-hidden="true" />
      <LanguageSwitch className="is-corner" />
      <main className="landing-main">
        <img className="landing-logo" src="/moh-logo.png" alt={t("common.ministry")} />
        <p className="landing-kicker">{t("common.lab")}</p>
        <h1 className="landing-title">
          {t("common.tagline")}{" "}
          <br />
          <span className="landing-title-accent">{t("common.taglineAccent")}</span>
        </h1>
        <p className="landing-lead">{t("landing.lead")}</p>
        <div className="landing-actions">
          <Link to="/upload" className="landing-cta">
            {t("landing.start")}
            <span aria-hidden="true">{t("common.forward")}</span>
          </Link>
          <Link to="/records" className="landing-secondary">
            {t("common.toRecords")}
          </Link>
        </div>

        <ol className="landing-steps">
          {STEPS.map((step, index) => (
            <li key={step.title} className="landing-step" style={{ animationDelay: `${150 + index * 120}ms` }}>
              <span className="landing-step-icon">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  {step.icon}
                </svg>
              </span>
              <span className="landing-step-number" aria-hidden="true">
                {index + 1}
              </span>
              <h2 className="landing-step-title">{step.title}</h2>
              <p className="landing-step-text">{step.text}</p>
            </li>
          ))}
        </ol>
      </main>
      <footer className="landing-footer">{t("common.footer")}</footer>
    </div>
  );
}

export default LandingPage;
