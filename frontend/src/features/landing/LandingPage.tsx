// The landing page: the ministry's logo, what the system does in three steps, and
// the way in to the upload. No data, no calls to the server.
// Owner: shared

import { Link } from "react-router";
import "./LandingPage.css";

const STEPS = [
  {
    title: "מעלים טפסים",
    text: "קבצי PDF או תמונות של טפסי התחייבות, כמה שרוצים בבת אחת",
    icon: (
      <>
        <path d="M12 16V4" />
        <path d="m6 10 6-6 6 6" />
        <path d="M4 20h16" />
      </>
    ),
  },
  {
    title: "המערכת קוראת",
    text: "שבעה שדות מכל טופס, גם בכתב יד, וכל ערך מפוקפק מסומן לבדיקה",
    icon: (
      <>
        <rect x="4" y="3" width="16" height="18" rx="2" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </>
    ),
  },
  {
    title: "בודקים ומאשרים",
    text: "רואים כל שדה ליד הטופס המקורי, מתקנים, מאשרים ומייצאים",
    icon: <path d="M5 12.5 10 17l9-10" />,
  },
];

export function LandingPage() {
  return (
    <div className="landing">
      <div className="landing-glow" aria-hidden="true" />
      <main className="landing-main">
        <img className="landing-logo" src="/moh-logo.png" alt="משרד הבריאות" />
        <p className="landing-kicker">המעבדה המרכזית לנגיפים</p>
        <h1 className="landing-title">
          מטופס סרוק{" "}
          <br />
          <span className="landing-title-accent">לרשומה מאושרת</span>
        </h1>
        <p className="landing-lead">
          מעלים את טפסי ההתחייבות, המערכת קוראת מהם את הנתונים, ואתם רק בודקים ומאשרים.
        </p>
        <div className="landing-actions">
          <Link to="/upload" className="landing-cta">
            התחלה: העלאת טפסים
            <span aria-hidden="true">←</span>
          </Link>
          <Link to="/records" className="landing-secondary">
            לכל הרשומות
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
      <footer className="landing-footer">משרד הבריאות · המעבדה המרכזית לנגיפים</footer>
    </div>
  );
}

export default LandingPage;
