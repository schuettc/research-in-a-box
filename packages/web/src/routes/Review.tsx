import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  ApiRefused,
  decide,
  heldFiles,
  type Decision,
  type HeldFile,
  type Submission,
} from "../api";
import { signedInSub } from "../auth";
import { History } from "../Findings";
import { FINAL_STATUSES, formatSize, statusLabel } from "../labels";
import { Modal, PageHeading, useTitle } from "../page";
import { usePeople } from "../People";
import { Preview } from "../Preview";
import { Checks, useSubmission } from "./Submission";
import { enteredReview, heldTitle, isHeld } from "./ReviewQueue";

/**
 * Whether the curator's page should read the submission again: the pipeline is at work, or a
 * submission in review isn't ready for a decision yet (after a first approval, until the
 * pipeline waits for the second).
 */
function moving(submission: Submission): boolean {
  if (FINAL_STATUSES.includes(submission.status)) return false;
  if (submission.status === "in-review") return !submission.waiting;
  return submission.status === "checking" || submission.status === "publishing";
}

/** Held links last five minutes: they are asked for again a little before. */
const HELD_REFRESH_MS = 4 * 60_000;

function useHeld(id: string, status: Submission["status"] | null) {
  const [held, setHeld] = useState<{ files: HeldFile[]; title: string | null } | null>(null);
  const holding = status !== null && isHeld(status);
  useEffect(() => {
    if (!holding) return;
    let current = true;
    const read = () => {
      Promise.all([heldFiles(id), heldTitle(id).catch(() => null)]).then(
        ([answer, title]) => current && setHeld({ files: answer.files, title }),
        () => {},
      );
    };
    read();
    const timer = setInterval(read, HELD_REFRESH_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, [id, holding]);
  return holding ? held : null;
}

const ACTIONS: { decision: Decision; label: string; heading: string; needsNote: boolean }[] = [
  { decision: "approve", label: "Approve", heading: "Approve this submission?", needsNote: false },
  {
    decision: "request-changes",
    label: "Request changes",
    heading: "Ask for changes?",
    needsNote: true,
  },
  { decision: "reject", label: "Reject", heading: "Reject this submission?", needsNote: true },
];

/** The modal that asks for a decision's note and confirms it, or shows why it was refused. */
function DecisionModal({
  id,
  action,
  onClose,
  onDecided,
}: {
  id: string;
  action: (typeof ACTIONS)[number];
  onClose: () => void;
  onDecided: () => void;
}) {
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const missing = action.needsNote && note.trim() === "";

  function confirm() {
    setSending(true);
    decide(id, action.decision, note.trim() || undefined).then(onDecided, (error: unknown) => {
      setSending(false);
      setRefused(
        error instanceof ApiRefused
          ? (error.reason ?? error.message)
          : "The archive can't be reached right now.",
      );
    });
  }

  return (
    <Modal label="decision-heading" onClose={onClose}>
      <h2 id="decision-heading">{action.heading}</h2>
      {refused ? (
        <>
          <p role="alert" className="problem">
            The archive didn't take it: {refused}.
          </p>
          <p className="actions">
            <button type="button" className="primary" autoFocus onClick={onDecided}>
              Reload
            </button>
            <button type="button" onClick={onClose}>
              Close
            </button>
          </p>
        </>
      ) : (
        <>
          <label className="field wide">
            <span>
              Note to the contributor{" "}
              <span className="muted">{action.needsNote ? "(required)" : "(optional)"}</span>
            </span>
            <textarea
              rows={4}
              value={note}
              required={action.needsNote}
              autoFocus
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <p className="actions">
            <button
              type="button"
              className="primary"
              disabled={missing || sending}
              onClick={confirm}
            >
              {action.label}
            </button>
            <button type="button" onClick={onClose}>
              Cancel
            </button>
          </p>
        </>
      )}
    </Modal>
  );
}

/** `/review/<id>`: a curator's view of one submission, and its decision. */
export function Review({ id }: { id: string }) {
  const { read, failed, reload } = useSubmission(id, moving);
  const held = useHeld(id, read?.submission.status ?? null);
  const [asking, setAsking] = useState<(typeof ACTIONS)[number] | null>(null);
  const [preview, setPreview] = useState<HeldFile | null>(null);
  const me = signedInSub();
  const name = usePeople(read ? [read.submission.submitter] : []);
  const title = held?.title ?? read?.submission.datasetId ?? "Review";
  useTitle(read ? `Review: ${title}` : "Review");

  if (!read) {
    if (failed === 403 || failed === 404) {
      return (
        <>
          <PageHeading>Submission not found</PageHeading>
          <p>
            There's no submission {id}. <Link to="/review">The review queue</Link>.
          </p>
        </>
      );
    }
    return (
      <>
        <PageHeading>Review</PageHeading>
        {failed === null ? (
          <p role="status" className="muted">
            Loading the submission…
          </p>
        ) : (
          <>
            <p role="alert">This submission can't be loaded right now.</p>
            <p className="actions">
              <button type="button" className="primary" onClick={reload}>
                Try again
              </button>
            </p>
          </>
        )}
      </>
    );
  }

  const submission = read.submission;
  const entered = enteredReview(read.events, submission.round);
  const needed = entered?.outcome === "two" ? 2 : 1;
  const approvedByMe = me !== null && submission.approvals.includes(me);
  const inReview = submission.status === "in-review";

  return (
    <>
      <PageHeading>{title}</PageHeading>
      <p className="status-line">
        {statusLabel(submission.status)}
        {submission.stale && (
          <>
            {" "}
            <span className="tag stale">Stale</span>
          </>
        )}
      </p>
      <p className="muted">
        From {name(submission.submitter)} · round {submission.round} ·{" "}
        {submission.newVersion ? (
          <>
            a new version of{" "}
            <Link to={`/datasets/${encodeURIComponent(submission.datasetId ?? "")}`}>
              {submission.datasetId}
            </Link>
          </>
        ) : (
          <>
            a new dataset <code>{submission.datasetId}</code>
          </>
        )}
        {inReview && (
          <>
            {" "}
            · needs {needed === 2 ? "two curators" : "one curator"}, {submission.approvals.length}{" "}
            approved
          </>
        )}{" "}
        · <Link to="/review">The review queue</Link>
      </p>
      {inReview && (
        <div className="note decision">
          {approvedByMe ? (
            needed === 2 && submission.approvals.length < 2 ? (
              <p>You approved it; it waits for a second curator.</p>
            ) : (
              <p>You approved it; it's being published.</p>
            )
          ) : !submission.waiting ? (
            <p>The archive is getting ready for the next decision; this page checks again.</p>
          ) : submission.approvals.length > 0 ? (
            <p>One curator approved it; a second approval publishes it.</p>
          ) : (
            <p>Read the findings and the files, then decide.</p>
          )}
          <p className="actions">
            {ACTIONS.map((action) => (
              <button
                key={action.decision}
                type="button"
                className={action.decision === "approve" ? "primary" : undefined}
                disabled={!submission.waiting || (action.decision === "approve" && approvedByMe)}
                onClick={() => setAsking(action)}
              >
                {action.label}
              </button>
            ))}
          </p>
        </div>
      )}
      <Checks read={read} />
      {isHeld(submission.status) && (
        <section className="block" aria-labelledby="files-heading">
          <h2 id="files-heading">Held files</h2>
          {held === null ? (
            <p role="status" className="muted">
              Reading the held files…
            </p>
          ) : (
            <ul className="files held" aria-label="Held files">
              {held.files.map((file) => (
                <li key={file.path} className="file">
                  <p className="file-head">
                    <code>{file.path}</code>
                  </p>
                  <p className="file-about">{formatSize(file.size)}</p>
                  <p className="file-action">
                    {file.path.toLowerCase().endsWith(".csv") && (
                      <button
                        type="button"
                        className="link-button"
                        aria-label={`Preview ${file.path}`}
                        onClick={() => setPreview(file)}
                      >
                        Preview
                      </button>
                    )}{" "}
                    <a
                      className="button download"
                      href={file.url}
                      aria-label={`Download ${file.path}`}
                    >
                      Download
                    </a>
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      <section className="block" aria-labelledby="history-heading">
        <h2 id="history-heading">History</h2>
        <History events={read.events} />
      </section>
      {asking && (
        <DecisionModal
          id={id}
          action={asking}
          onClose={() => setAsking(null)}
          onDecided={() => {
            setAsking(null);
            reload();
          }}
        />
      )}
      {preview && (
        <Modal label="preview-heading" wide onClose={() => setPreview(null)}>
          <h2 id="preview-heading">{preview.path}: the first rows</h2>
          <Preview url={preview.url} size={preview.size} />
          <p className="actions">
            <button type="button" autoFocus onClick={() => setPreview(null)}>
              Close
            </button>
          </p>
        </Modal>
      )}
    </>
  );
}
