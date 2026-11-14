import { useState } from "react";
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
 * The optional "how will you use this data?" panel shown after a download starts. It never
 * blocks the download, asks for nothing identifying, and is shown once per visit.
 */
export function UsagePanel({ datasetId, onClose }: { datasetId: string; onClose: () => void }) {
  const [organisation, setOrganisation] = useState("");
  const [purpose, setPurpose] = useState("");
  const [note, setNote] = useState("");
  const [sent, setSent] = useState(false);

  function finish() {
    sessionStorage.setItem(DONE_KEY, "1");
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

  if (sent) return <p className="usage">Thanks, your answers were sent anonymously.</p>;

  return (
    <section className="usage" aria-labelledby="usage-heading">
      <h2 id="usage-heading">Help this archive: how will you use this data?</h2>
      <p className="hint">All optional. We don't ask who you are.</p>
      <div className="usage-fields">
        <label className="field">
          Kind of organisation
          <select value={organisation} onChange={(event) => setOrganisation(event.target.value)}>
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
        <button
          type="button"
          onClick={() => {
            finish();
            onClose();
          }}
        >
          No thanks
        </button>
      </div>
    </section>
  );
}
