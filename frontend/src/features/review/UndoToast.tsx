// The small note at the bottom after approve or delete: what was done, and "ביטול"
// while it still waits (useUndo). A refusal from the server shows here too.
// Owner: B

import { t } from "../../i18n";
import { UNDO_MS, type Undoable } from "./useUndo";
import "./UndoToast.css";

interface Props {
  waiting: Undoable | null;
  error: string | null;
  onUndo: () => void;
  onDismiss: () => void;
}

export function UndoToast({ waiting, error, onUndo, onDismiss }: Props) {
  return (
    // Always in the page, so the screen reader hears each new note.
    <div className="undo-toast-area" role="status" aria-live="polite">
      {waiting && (
        <div className="undo-toast" key={waiting.text}>
          <span className="undo-toast-text">{waiting.text}</span>
          <button type="button" className="undo-toast-button" onClick={onUndo}>
            {t("common.cancel")}
          </button>
          <span className="undo-toast-timer" style={{ animationDuration: `${UNDO_MS}ms` }} aria-hidden="true" />
        </div>
      )}
      {!waiting && error && (
        <div className="undo-toast is-error">
          <span className="undo-toast-text">{error}</span>
          <button type="button" className="undo-toast-button" onClick={onDismiss}>
            {t("common.close")}
          </button>
        </div>
      )}
    </div>
  );
}

export default UndoToast;
