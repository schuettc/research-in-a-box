import { useEffect, useState } from "react";
import { Link } from "react-router";
import {
  ApiRefused,
  getSubmission,
  type FindingsReport,
  type Submission as Item,
  type SubmissionEvent,
  type SubmissionRead,
} from "../api";
import { Findings, History } from "../Findings";
import { FINAL_STATUSES, statusLine } from "../labels";
import { Modal, PageHeading, useTitle } from "../page";
import { PackageFlow } from "./Submit";

/** How often a submission is read again while something can still change on its own. */
export const POLL_MS = 10_000;

/**
 * Whether the contributor's page should read the submission again: the pipeline is at work.
 * A draft changes only when the contributor acts, and acting reads it again.
 */
function moving(submission: Item): boolean {
  if (FINAL_STATUSES.includes(submission.status)) return false;
  if (submission.status === "draft") return false;
  if (submission.status === "needs-changes") return !submission.waiting;
  return true;
}

/** The latest curator's note asking for changes, if the submission waits on them. */
function changesNote(events: SubmissionEvent[]): string | null {
  const decided = events
    .filter((event) => event.type === "decided" && event.decision === "request-changes")
    .toSorted((a, b) => a.eventKey.localeCompare(b.eventKey))
    .at(-1);
  return decided?.note ?? null;
}

/** Whether the last check of the current round blocked it with errors. */
function blocked(read: SubmissionRead): boolean {
  const checked = read.events
    .filter((event) => event.type === "checked" && event.round === read.submission.round)
    .at(-1);
  return Boolean(checked?.blocked);
}

const day = (at: string) =>
  new Date(at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

/** A submission's findings report, read once per report (its link changes on every read). */
function useReport(read: SubmissionRead | null): FindingsReport | "failed" | null {
  const key = read?.submission.reportKey ?? null;
  const url = read?.reportUrl ?? null;
  const [report, setReport] = useState<{ key: string; report: FindingsReport | "failed" } | null>(
    null,
  );
  const have = report?.key === key;
  useEffect(() => {
    if (!key || !url || have) return;
    let current = true;
    fetch(url)
      .then((response) => {
        if (!response.ok) throw new Error(String(response.status));
        return response.json() as Promise<FindingsReport>;
      })
      .then(
        (found) => current && setReport({ key, report: found }),
        () => current && setReport({ key, report: "failed" }),
      );
    return () => {
      current = false;
    };
  }, [key, url, have]);
  return have ? report.report : null;
}

/**
 * A submission read now and every 10 s while the pipeline is still at work on it (`moving`),
 * stopping once nothing can change without the reader. `reload` reads it again at once.
 * `keepReading` should be a module-level function, so it is the same on every render.
 */
export function useSubmission(
  id: string,
  keepReading: (submission: Item) => boolean,
): { read: SubmissionRead | null; failed: number | null; reload: () => void } {
  const [read, setRead] = useState<SubmissionRead | null>(null);
  const [failed, setFailed] = useState<number | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let current = true;
    const tick = () => {
      getSubmission(id).then(
        (answer) => {
          if (!current) return;
          setRead(answer);
          setFailed(null);
          if (keepReading(answer.submission)) timer = setTimeout(tick, POLL_MS);
        },
        (error: unknown) => {
          if (!current) return;
          setFailed(error instanceof ApiRefused ? error.status : 0);
        },
      );
    };
    tick();
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [id, attempt, keepReading]);
  return { read, failed, reload: () => setAttempt((n) => n + 1) };
}

/** The checks section: the report once read, or why it isn't shown. */
export function Checks({ read }: { read: SubmissionRead }) {
  const report = useReport(read);
  return (
    <section className="block" aria-labelledby="checks-heading">
      <h2 id="checks-heading">Checks</h2>
      {!read.submission.reportKey ? (
        <p className="muted">The files haven't been checked yet.</p>
      ) : report === "failed" ? (
        <p role="alert">The findings report can't be read right now.</p>
      ) : report ? (
        <Findings report={report} />
      ) : (
        <p role="status" className="muted">
          Reading the findings…
        </p>
      )}
    </section>
  );
}

/** `/submissions/<id>`: where the contributor's submission stands, its checks and its history. */
export function Submission({ id }: { id: string }) {
  const { read, failed, reload } = useSubmission(id, moving);
  const [flow, setFlow] = useState(false);
  const title = read?.submission.datasetId ?? "Submission";
  useTitle(read ? title : "Submission");

  if (!read) {
    if (failed === 403 || failed === 404) {
      return (
        <>
          <PageHeading>Submission not found</PageHeading>
          <p>
            There's no submission {id} of yours. <Link to="/submissions">My submissions</Link>.
          </p>
        </>
      );
    }
    return (
      <>
        <PageHeading>Submission</PageHeading>
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
  const note = submission.status === "needs-changes" ? changesNote(read.events) : null;
  const draft = submission.status === "draft";
  return (
    <>
      <PageHeading>{title}</PageHeading>
      <p className="status-line">{statusLine(submission.status)}</p>
      <p className="muted">
        Round {submission.round} · started {day(submission.createdAt)} ·{" "}
        {submission.newVersion ? "a new version" : "a new dataset"} ·{" "}
        <Link to="/submissions">My submissions</Link>
      </p>
      {submission.status === "needs-changes" && (
        <div className="note">
          {note ? (
            <>
              <p className="label">The curator's note</p>
              <p className="curator-note">{note}</p>
            </>
          ) : (
            blocked(read) && <p>The checks found errors to fix before a curator sees it.</p>
          )}
          <p className="actions">
            <button
              type="button"
              className="primary"
              disabled={!submission.waiting}
              onClick={() => setFlow(true)}
            >
              Resubmit
            </button>
          </p>
          {!submission.waiting && (
            <p className="hint">
              The archive is getting ready for your next round; this page checks again every 10
              seconds.
            </p>
          )}
        </div>
      )}
      {draft && (
        <div className="note">
          <p>
            This round isn't submitted: not every file was uploaded, or the upload links ran out.
            Choose the folder again for new links.
          </p>
          <p className="actions">
            <button type="button" className="primary" onClick={() => setFlow(true)}>
              Choose the folder again
            </button>
          </p>
        </div>
      )}
      <Checks read={read} />
      <section className="block" aria-labelledby="history-heading">
        <h2 id="history-heading">History</h2>
        <History events={read.events} />
      </section>
      {flow && (
        <Modal label="flow-heading" wide onClose={() => setFlow(false)}>
          <h2 id="flow-heading">
            {draft ? "Choose the folder again" : `Round ${submission.round + 1}`}
          </h2>
          <PackageFlow
            mode={{ kind: "round", submission }}
            onDone={() => {
              setFlow(false);
              reload();
            }}
          />
          <p className="actions">
            <button type="button" onClick={() => setFlow(false)}>
              Close
            </button>
          </p>
        </Modal>
      )}
    </>
  );
}
