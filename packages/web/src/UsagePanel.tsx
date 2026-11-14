import { useEffect, useRef, useState } from "react";
import { sendUsage, type UsageAnswers } from "./api";

const DONE_KEY = "usage-panel-done";

const ORGANISATIONS = [
  ["university", "University"],
  ["government", "Government"],
  ["nonprofit", "Non-profit"],
  ["company", "Company"],
  ["individual", "Individual"],
  ["other", "Other"],
] as const;
const PURPOSES = [
  ["research", "Research"],
  ["teaching", "Teaching"],
  ["policy-or-management", "Policy or management"],
  ["commercial", "Commercial"],
  ["personal", "Personal"],
  ["other", "Other"],
] as const;

/** Whether the reader has answered or dismissed the panel in this visit. */
export function usagePanelDone(): boolean {
  return sessionStorage.getItem(DONE_KEY) === "1";
}

/**
 * The optional "how will you use this data?" question, a modal dialog opened after a download
 * starts. It overlays the page rather than pushing it down, never blocks the download, asks
 * for nothing identifying, and is shown once per visit. Escape or No thanks dismisses it.
 */
export function UsagePanel({ datasetId, onClose }: { datasetId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [organisation, setOrganisation] = useState("");
  const [purpose, setPurpose] = useState("");
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);

  useEffect(() => {
    const element = dialog.current;
    if (element && !element.open) element.showModal();
  }, []);

  function finish() {
    sessionStorage.setItem(DONE_KEY, "1");
  }

  function dismiss() {
    finish();
    onClose();
  }

  function send() {
    finish();
    const answers: UsageAnswers = {};
    if (organisation) answers.organisation = organisation as UsageAnswers["organisation"];
    if (purpose) answers.purpose = purpose as UsageAnswers["purpose"];
    if (note.trim()) answers.note = note.trim();
    // The answers are a courtesy; a failed send isn't worth troubling the reader with.
    sendUsage(datasetId, answers).catch(() => {});
    setSent(true);
  }

  return (
    <dialog
      ref={dialog}
      className="usage"
      aria-labelledby="usage-heading"
      onCancel={(event) => {
        event.preventDefault();
        dismiss();
      }}
    >
      {sent ? (
        <>
          <p className="usage-thanks" role="status">
            Thanks, your answers were sent anonymously.
          </p>
          <div className="actions">
            <button type="button" className="primary" autoFocus onClick={onClose}>
              Close
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="usage-started">Your download has started.</p>
          <h2 id="usage-heading">Help this archive: how will you use this data?</h2>
          <p className="hint">All optional. We don't ask who you are.</p>
          <div className="usage-fields">
            <label className="field">
              Kind of organisation
              <select
                value={organisation}
                onChange={(event) => setOrganisation(event.target.value)}
              >
                <option value="">Choose…</option>
                {ORGANISATIONS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Purpose
              <select value={purpose} onChange={(event) => setPurpose(event.target.value)}>
                <option value="">Choose…</option>
                {PURPOSES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field wide">
              <span>
                Note <span className="muted">(optional)</span>
              </span>
              <textarea
                rows={2}
                maxLength={500}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
          </div>
          <div className="actions">
            <button type="button" className="primary" onClick={send}>
              Send
            </button>
            <button type="button" onClick={dismiss}>
              No thanks
            </button>
          </div>
        </>
      )}
    </dialog>
  );
}
