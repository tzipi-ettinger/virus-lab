// Switches between Hebrew and English: shows the other language, in that language,
// and loads the page again in it (i18n/index.ts).
// Owner: B

import { chooseLanguage, language, t } from "../../i18n";
import "./LanguageSwitch.css";

export function LanguageSwitch({ className = "" }: { className?: string }) {
  const other = language === "he" ? "en" : "he";
  return (
    <button
      type="button"
      className={`language-switch ${className}`.trim()}
      lang={other}
      aria-label={t("language.switchTo")}
      title={t("language.switchTo")}
      onClick={() => chooseLanguage(other)}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3" />
      </svg>
      {t("language.other")}
    </button>
  );
}
