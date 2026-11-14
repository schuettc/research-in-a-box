import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import {
  getSubmission,
  heldFiles,
  listSubmissions,
  type Submission,
  type SubmissionEvent,
} from "../api";
import { STATUSES, statusLabel, type Status } from "../labels";
import { PageHeading, useTitle } from "../page";
import { usePeople } from "../People";

/** Whether the held copy of a submission is there to read: only in review or publishing. */
export function isHeld(status: Status): boolean {
  return status === "in-review" || status === "publishing";
}

/** The title from a held submission's manifest, read through its held file's link. */
export async function heldTitle(id: string): Promise<string | null> {
  const held = await heldFiles(id);
  const manifest = held.files.find((file) => file.path === "datapackage.json");
  if (!manifest) return null;
  const response = await fetch(manifest.url);
  if (!response.ok) return null;
  const parsed = (await response.json()) as { title?: unknown };
  return typeof parsed.title === "string" ? parsed.title : null;
}

/** The current round's `entered-review` event: how many curators it needs, and whom it asks. */
export function enteredReview(events: SubmissionEvent[], round: number): SubmissionEvent | null {
  return (
    events
      .filter((event) => event.type === "entered-review" && event.round === round)
      .toSorted((a, b) => a.eventKey.localeCompare(b.eventKey))
      .at(-1) ?? null
  );
}

/** What a queue row reads beyond the list: the title and the review's needs. */
interface RowDetail {
  title: string | null;
  needed: number | null;
  audience: string | null;
}

function QueueRow({ submission }: { submission: Submission }) {
  const [detail, setDetail] = useState<RowDetail | null>(null);
  const id = submission.submissionId;
  const held = isHeld(submission.status);
  useEffect(() => {
    let current = true;
    Promise.all([
      getSubmission(id).catch(() => null),
      held ? heldTitle(id).catch(() => null) : Promise.resolve(null),
    ]).then(([read, title]) => {
      if (!current) return;
      const entered = read ? enteredReview(read.events, submission.round) : null;
      setDetail({
        title,
        needed: entered?.outcome === "two" ? 2 : entered?.outcome === "one" ? 1 : null,
        audience: entered?.audience ?? null,
      });
    });
    return () => {
      current = false;
    };
  }, [id, held, submission.round]);
  const audience = detail?.audience;
  const name = usePeople(
    [submission.submitter, audience && audience !== "all" ? audience : ""].filter(Boolean),
  );

  return (
    <tr>
      <th scope="row">
        <Link to={`/review/${encodeURIComponent(id)}`}>
          {detail?.title ?? submission.datasetId ?? id}
        </Link>
        {submission.stale && (
          <>
            {" "}
            <span className="tag stale">Stale</span>
          </>
        )}
        {detail?.title && submission.datasetId && (
          <span className="queue-id">
            <code>{submission.datasetId}</code>
          </span>
        )}
      </th>
      <td>{name(submission.submitter)}</td>
      <td>{submission.round}</td>
      <td>{submission.newVersion ? "New version" : "New dataset"}</td>
      <td>
        {detail === null
          ? "…"
          : detail.needed === null
            ? "—"
            : `${submission.approvals.length} of ${detail.needed} approved`}
      </td>
      <td>{audience == null ? "—" : audience === "all" ? "Any curator" : name(audience)}</td>
    </tr>
  );
}

const DEFAULT_STATUS: Status = "in-review";

/** `/review`: the curators' queue for one status, in review by default. */
export function ReviewQueue() {
  useTitle("Review queue");
  const [params, setParams] = useSearchParams();
  const asked = params.get("status");
  const status: Status = STATUSES.includes(asked as Status) ? (asked as Status) : DEFAULT_STATUS;
  const [loaded, setLoaded] = useState<{ status: Status; list: Submission[] | "failed" } | null>(
    null,
  );
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let current = true;
    listSubmissions({ status }).then(
      (answer) =>
        current &&
        setLoaded({
          status,
          list: answer.submissions.toSorted((a, b) => a.createdAt.localeCompare(b.createdAt)),
        }),
      () => current && setLoaded({ status, list: "failed" }),
    );
    return () => {
      current = false;
    };
  }, [status, attempt]);

  const list = loaded?.status === status ? loaded.list : null;
  return (
    <>
      <PageHeading>Review queue</PageHeading>
      <div className="queue-filter">
        <label className="field">
          Status
          <select
            value={status}
            onChange={(event) =>
              setParams(event.target.value === DEFAULT_STATUS ? {} : { status: event.target.value })
            }
          >
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {statusLabel(value)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {list === "failed" ? (
        <>
          <p role="alert">The queue can't be loaded right now.</p>
          <p className="actions">
            <button type="button" onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </button>
          </p>
        </>
      ) : list === null ? (
        <p role="status" className="muted">
          Loading the queue…
        </p>
      ) : list.length === 0 ? (
        <p>Nothing is {statusLabel(status).toLowerCase()} right now.</p>
      ) : (
        <div className="table-scroll">
          <table className="cols listing queue">
            <thead>
              <tr>
                <th scope="col">Dataset</th>
                <th scope="col">Submitted by</th>
                <th scope="col">Round</th>
                <th scope="col">Kind</th>
                <th scope="col">Curators</th>
                <th scope="col">Assigned to</th>
              </tr>
            </thead>
            <tbody>
              {list.map((submission) => (
                <QueueRow key={submission.submissionId} submission={submission} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
