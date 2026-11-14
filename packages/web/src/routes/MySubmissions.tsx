import { useEffect, useState } from "react";
import { Link } from "react-router";
import { getSubmission, listSubmissions, type Submission } from "../api";
import { statusLabel } from "../labels";
import { PageHeading, useTitle } from "../page";

const day = (at: string) =>
  new Date(at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

/** The time of a submission's latest event, read from its own page's answer. */
function LastChange({ submission }: { submission: Submission }) {
  const [at, setAt] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    getSubmission(submission.submissionId).then(
      (read) => {
        const last = read.events
          .map((event) => event.at)
          .toSorted()
          .at(-1);
        if (current) setAt(last ?? submission.createdAt);
      },
      () => current && setAt(submission.createdAt),
    );
    return () => {
      current = false;
    };
  }, [submission.submissionId, submission.createdAt]);
  return at ? <time dateTime={at}>{day(at)}</time> : <span className="muted">…</span>;
}

/** `/submissions`: the contributor's own submissions, newest first, with where each stands. */
export function MySubmissions() {
  useTitle("My submissions");
  const [list, setList] = useState<Submission[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    listSubmissions({ mine: true }).then(
      (answer) => {
        if (!current) return;
        setList(answer.submissions.toSorted((a, b) => b.createdAt.localeCompare(a.createdAt)));
        setFailed(false);
      },
      () => current && setFailed(true),
    );
    return () => {
      current = false;
    };
  }, [attempt]);

  return (
    <>
      <PageHeading>My submissions</PageHeading>
      <p className="actions page-actions">
        <Link className="button primary" to="/submit">
          Submit a package
        </Link>
      </p>
      {failed ? (
        <>
          <p role="alert">Your submissions can't be loaded right now.</p>
          <p className="actions">
            <button type="button" onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </button>
          </p>
        </>
      ) : list === null ? (
        <p role="status" className="muted">
          Loading your submissions…
        </p>
      ) : list.length === 0 ? (
        <p>You haven't submitted a package yet.</p>
      ) : (
        <div className="table-scroll">
          <table className="cols listing">
            <thead>
              <tr>
                <th scope="col">Dataset</th>
                <th scope="col">Round</th>
                <th scope="col">Status</th>
                <th scope="col">Last change</th>
              </tr>
            </thead>
            <tbody>
              {list.map((submission) => (
                <tr key={submission.submissionId}>
                  <th scope="row">
                    <Link to={`/submissions/${encodeURIComponent(submission.submissionId)}`}>
                      {submission.datasetId ?? submission.submissionId}
                    </Link>
                  </th>
                  <td>{submission.round}</td>
                  <td>{statusLabel(submission.status)}</td>
                  <td>
                    <LastChange submission={submission} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
