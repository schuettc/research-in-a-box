import type { Finding, FindingsReport, SubmissionEvent } from "./api";
import { decisionLabel, eventLabel } from "./labels";
import { usePeople } from "./People";

const SEVERITIES = [
  ["error", "Errors"],
  ["warning", "Warnings"],
  ["note", "Notes"],
] as const;

const plural = (count: number, one: string) => `${count} ${one}${count === 1 ? "" : "s"}`;

/** What a finding is about: "logger › site_id", or a file's path. */
function where(finding: Finding): string | null {
  const target = finding.target;
  if (!target) return null;
  const parts = [target.resource, target.field].filter(Boolean);
  if (parts.length) return parts.join(" › ");
  return target.path ?? null;
}

function evidence(finding: Finding): string | null {
  const found = finding.evidence;
  if (!found) return null;
  const parts: string[] = [];
  if (found.rows?.length) parts.push(`rows ${found.rows.join(", ")}`);
  if (found.values?.length) parts.push(`values ${found.values.map(String).join(", ")}`);
  if (typeof found.count === "number") parts.push(`${found.count} in all`);
  return parts.length ? parts.join(" · ") : null;
}

/**
 * A round's findings report: the score and counts, then the findings grouped error, warning,
 * note, each with what it is about and its suggested fix. The same Finding model cruise prints.
 */
export function Findings({ report }: { report: FindingsReport }) {
  const quality = report.quality;
  const count = (severity: string) =>
    report.findings.filter((finding) => finding.severity === severity).length;
  return (
    <div className="findings">
      <p className="checks-summary">
        {quality ? (
          <>
            <strong>{quality.score}%</strong> of the checks passed ·{" "}
            {plural(count("error"), "error")} · {plural(count("warning"), "warning")} ·{" "}
            {plural(count("note"), "note")}
          </>
        ) : report.validation ? (
          "The checks couldn't read the manifest, so there is no score."
        ) : (
          "The malware scan stopped this round before the checks ran."
        )}
      </p>
      {report.findings.length === 0 && <p className="muted">No findings.</p>}
      {SEVERITIES.map(([severity, heading]) => {
        const found = report.findings.filter((finding) => finding.severity === severity);
        if (found.length === 0) return null;
        return (
          <div key={severity} className={`finding-group severity-${severity}`}>
            <h3>
              {heading} ({found.length})
            </h3>
            <ul aria-label={heading} className="finding-list">
              {found.map((finding, index) => {
                const about = where(finding);
                const shown = evidence(finding);
                return (
                  <li key={`${finding.ruleId}-${index}`} className="finding">
                    <p className="finding-message">{finding.message}</p>
                    <p className="finding-meta">
                      {about && <code>{about}</code>}
                      {about && shown && " · "}
                      {shown}
                      <span className="rule-id">{finding.ruleId}</span>
                    </p>
                    {finding.suggestedFix && (
                      <p className="finding-fix">
                        <span className="label">fix</span> {finding.suggestedFix}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

const DETAIL_KEYS = ["eventKey", "at", "submissionId"];

/**
 * A retried step can record an event twice (Plan 7's PARK12): show each once. Two events alike
 * in everything but their time and key are one event.
 */
function deduplicated(events: SubmissionEvent[]): SubmissionEvent[] {
  const seen = new Set<string>();
  return events.filter((event) => {
    const key = JSON.stringify(
      Object.entries(event)
        .filter(([field]) => !DETAIL_KEYS.includes(field))
        .toSorted(([a], [b]) => a.localeCompare(b)),
    );
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** An event's details in words, beyond its type. */
function detail(event: SubmissionEvent): string | null {
  switch (event.type) {
    case "checked":
      if (event.blocked) return `blocked: ${plural(event.errors ?? 0, "error")} to fix`;
      return `${plural(event.errors ?? 0, "error")}, ${plural(event.warnings ?? 0, "warning")}, ${plural(event.notes ?? 0, "note")}`;
    case "scanned": {
      const threats = Object.keys(event.threats ?? {}).length;
      return threats
        ? `${plural(threats, "file")} flagged`
        : `${plural(event.files ?? 0, "file")}, none flagged`;
    }
    case "held":
      return plural(event.files ?? 0, "file");
    case "entered-review":
      return event.outcome === "two" ? "needs two curators" : "needs one curator";
    case "reminded":
      return `day ${event.day}`;
    case "stale":
      return `after ${event.days} days`;
    case "decided":
      return (
        decisionLabel(event.decision ?? "") + (event.selfReview ? " (their own submission)" : "")
      );
    case "published":
      return `as ${event.datasetId}, version ${event.version}`;
    case "failed":
      return event.error ?? null;
    default:
      return null;
  }
}

const when = (at: string) =>
  new Date(at).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

/** A submission's audit events, oldest first, with people named. */
export function History({ events }: { events: SubmissionEvent[] }) {
  const shown = deduplicated(events.toSorted((a, b) => a.eventKey.localeCompare(b.eventKey)));
  const name = usePeople(shown.map((event) => event.actor));
  if (shown.length === 0) return <p className="muted">Nothing has happened yet.</p>;
  return (
    <ol aria-label="History" className="history">
      {shown.map((event) => {
        const said = detail(event);
        const note = event.note;
        return (
          <li key={event.eventKey}>
            <time dateTime={event.at}>{when(event.at)}</time>
            <span>
              {eventLabel(event.type)}
              {event.actor !== "pipeline" && ` by ${name(event.actor)}`}
              {said && <span className="muted"> · {said}</span>}
              {event.round > 1 && <span className="muted"> · round {event.round}</span>}
              {note && <q className="history-note">{note}</q>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
