import { useRef, useState, type DragEvent } from "react";
import { flushSync } from "react-dom";
import { Link, useNavigate } from "react-router";
import {
  ApiRefused,
  createSubmission,
  getDataset,
  renewUploads,
  submitRound,
  type Submission,
  type UploadsAnswer,
} from "../api";
import { formatSize } from "../labels";
import {
  checkPackage,
  droppedEntries,
  fromEntries,
  fromFileList,
  uploadFile,
  type PackageFile,
  type ReadyFile,
} from "../package";
import { PageHeading, useTitle } from "../page";

/** A new submission, or the next round (or new links) for one that exists. */
export type FlowMode = { kind: "new" } | { kind: "round"; submission: Submission };

type Ready = {
  files: ReadyFile[];
  left: string[];
  id: string;
  title: string | null;
  /** Whether the dataset is already published: a new version, a new dataset, or unknown. */
  kind: "new" | "version" | "unknown";
};

type Phase =
  | { at: "choose"; problem: string | null }
  | { at: "checking"; done: number; total: number }
  | { at: "ready"; ready: Ready }
  | { at: "sending"; ready: Ready; error: string | null };

/** The words for a failure while sending: the API's own, or what went wrong with an upload. */
function failure(error: unknown): string {
  if (error instanceof ApiRefused) {
    return error.reason ? `The archive refused it: ${error.reason}.` : error.message;
  }
  if (error instanceof Error && error.message.startsWith("the upload")) {
    return `An upload didn't finish: ${error.message}.`;
  }
  return "The archive can't be reached right now.";
}

async function datasetKind(id: string): Promise<Ready["kind"]> {
  try {
    await getDataset(id);
    return "version";
  } catch (error) {
    return error instanceof ApiRefused && error.status === 404 ? "new" : "unknown";
  }
}

/**
 * Choose or drop a package folder, check it, then create the submission (or its next round),
 * upload every file to its link with a progress bar, and submit. `onDone` hears the
 * submission's id once it is submitted.
 */
export function PackageFlow({
  mode,
  onDone,
}: {
  mode: FlowMode;
  onDone: (submissionId: string) => void;
}) {
  const [phase, setPhase] = useState<Phase>({ at: "choose", problem: null });
  const [sent, setSent] = useState<Record<string, number>>({});
  const [dragging, setDragging] = useState(false);
  // The submission once created, so Try again asks for new links rather than a second one.
  const created = useRef<string | null>(
    mode.kind === "round" ? mode.submission.submissionId : null,
  );
  const uploaded = useRef(new Set<string>());

  async function check(files: PackageFile[]) {
    setPhase({ at: "checking", done: 0, total: files.length });
    const checked = await checkPackage(files, (done, total) =>
      setPhase({ at: "checking", done, total }),
    );
    if (!checked.ok) {
      setPhase({ at: "choose", problem: checked.problem });
      return;
    }
    const { id, title } = checked.manifest;
    if (mode.kind === "round" && mode.submission.datasetId && mode.submission.datasetId !== id) {
      setPhase({
        at: "choose",
        problem: `This folder is dataset ${id}, but the submission is for ${mode.submission.datasetId}.`,
      });
      return;
    }
    const kind =
      mode.kind === "round"
        ? mode.submission.newVersion
          ? "version"
          : "new"
        : await datasetKind(id);
    setPhase({ at: "ready", ready: { files: checked.files, left: checked.left, id, title, kind } });
  }

  async function send(ready: Ready) {
    setPhase({ at: "sending", ready, error: null });
    const meta = ready.files.map(({ path, size, sha256 }) => ({ path, size, sha256 }));
    try {
      let answer: UploadsAnswer;
      if (created.current) answer = await renewUploads(created.current, meta);
      else answer = await createSubmission(meta, ready.id);
      created.current = answer.submissionId;
      const byPath = new Map(ready.files.map((file) => [file.path, file]));
      for (const upload of answer.uploads) {
        const file = byPath.get(upload.path);
        if (!file || uploaded.current.has(upload.path)) continue;
        // Shown at once, so the bars are full before the round is submitted.
        await uploadFile(upload, file.file, (loaded) =>
          flushSync(() => setSent((now) => ({ ...now, [upload.path]: loaded }))),
        );
        uploaded.current.add(upload.path);
      }
      await submitRound(answer.submissionId);
      onDone(answer.submissionId);
    } catch (error) {
      setPhase({ at: "sending", ready, error: failure(error) });
    }
  }

  function chosen(list: FileList | null) {
    if (list?.length) void check(fromFileList(list));
  }

  function dropped(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const entries = droppedEntries(event.dataTransfer.items);
    if (entries.length) void fromEntries(entries).then(check);
  }

  if (phase.at === "choose" || phase.at === "checking") {
    return (
      <div
        className={dragging ? "dropzone over" : "dropzone"}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={dropped}
      >
        <p>Drop the package folder here, or choose it.</p>
        <label className="button primary choose">
          Choose folder
          <input
            type="file"
            multiple
            className="visually-hidden"
            ref={(input) => input?.setAttribute("webkitdirectory", "")}
            onChange={(event) => chosen(event.target.files)}
          />
        </label>
        <p className="hint">
          The folder needs datapackage.json and checksums.sha256 at its top, as cruise writes them.
        </p>
        {phase.at === "checking" ? (
          <p role="status" className="muted">
            Checking the files: {phase.done} of {phase.total}
          </p>
        ) : (
          phase.problem && (
            <p role="alert" className="problem">
              {phase.problem}
            </p>
          )
        )}
      </div>
    );
  }

  const ready = phase.ready;
  const total = ready.files.reduce((sum, file) => sum + file.size, 0);
  const sending = phase.at === "sending";
  const bytes = ready.files.reduce((sum, file) => sum + (sent[file.path] ?? 0), 0);
  const percent = total === 0 ? (sending ? 100 : 0) : Math.floor((bytes * 100) / total);

  return (
    <div className="package">
      <dl className="facts">
        <div>
          <dt>Dataset</dt>
          <dd>
            {ready.title && (
              <>
                <span>{ready.title}</span>
                <br />
              </>
            )}
            <code>{ready.id}</code>
          </dd>
        </div>
        <div>
          <dt>Kind</dt>
          <dd>
            {ready.kind === "version" ? (
              <>
                New version of{" "}
                <Link to={`/datasets/${encodeURIComponent(ready.id)}`}>{ready.id}</Link>
              </>
            ) : ready.kind === "new" ? (
              "New dataset"
            ) : (
              "Unknown: the archive couldn't say whether it is published"
            )}
          </dd>
        </div>
        <div>
          <dt>Files</dt>
          <dd>
            {ready.files.length} files, {formatSize(total)}, each matching checksums.sha256
          </dd>
        </div>
      </dl>
      {ready.left.length > 0 && (
        <p className="hint">
          Not sent, since checksums.sha256 doesn't list them: {ready.left.join(", ")}.
        </p>
      )}
      {sending ? (
        <>
          <div className="overall">
            <label htmlFor="all-files">All files</label>
            <progress id="all-files" max={100} value={percent} aria-label="All files" />
            <span className="muted">{percent}%</span>
          </div>
          <ul className="uploads" aria-label="Uploads">
            {ready.files.map((file) => (
              <li key={file.path}>
                <code>{file.path}</code>
                <progress
                  max={Math.max(file.size, 1)}
                  value={file.size === 0 ? (file.path in sent ? 1 : 0) : (sent[file.path] ?? 0)}
                  aria-label={file.path}
                />
              </li>
            ))}
          </ul>
          {phase.error && (
            <>
              <p role="alert" className="problem">
                {phase.error}
              </p>
              <p className="actions">
                <button type="button" className="primary" onClick={() => void send(ready)}>
                  Try again
                </button>
              </p>
            </>
          )}
        </>
      ) : (
        <p className="actions">
          <button type="button" className="primary" onClick={() => void send(ready)}>
            Upload and submit
          </button>
          <button type="button" onClick={() => setPhase({ at: "choose", problem: null })}>
            Choose another folder
          </button>
        </p>
      )}
    </div>
  );
}

/** `/submit`: send a package made with cruise for review. */
export function Submit() {
  useTitle("Submit");
  const navigate = useNavigate();
  return (
    <>
      <PageHeading>Submit a package</PageHeading>
      <p className="lede">
        Send a package made with cruise. The archive checks it, and a curator reviews it before it
        is published. <Link to="/submissions">My submissions</Link> shows where each one stands.
      </p>
      <PackageFlow
        mode={{ kind: "new" }}
        onDone={(id) => void navigate(`/submissions/${encodeURIComponent(id)}`)}
      />
    </>
  );
}
