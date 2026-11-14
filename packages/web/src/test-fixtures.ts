/** Fixtures the tests share: the sample package as a browser would give it, and a fake XHR. */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import type { FindingsReport, Submission as Item, SubmissionEvent } from "./api";

export const SAMPLE = join(import.meta.dirname, "../../../examples/sample-package");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** The sample package as a directory input gives it: each file under the folder's own name. */
export function sampleFiles(change?: Record<string, string>, leave: string[] = []): File[] {
  return walk(SAMPLE)
    .map((path) => relative(SAMPLE, path))
    .filter((path) => !leave.includes(path))
    .map((path) => {
      const content = change?.[path] ?? readFileSync(join(SAMPLE, path));
      const file = new File([content], path.split("/").pop() ?? path);
      Object.defineProperty(file, "webkitRelativePath", { value: `sample-package/${path}` });
      return file;
    });
}

/** A stand-in for XMLHttpRequest: records each request and reports progress, then load. */
export class FakeXhr {
  static sent: { method: string; url: string; headers: Record<string, string>; body: unknown }[] =
    [];
  static status = 200;
  upload: { onprogress: ((event: ProgressEvent) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  status = 0;
  private request = { method: "", url: "", headers: {} as Record<string, string> };
  open(method: string, url: string) {
    this.request = { method, url, headers: {} };
  }
  setRequestHeader(name: string, value: string) {
    this.request.headers[name.toLowerCase()] = value;
  }
  send(body: Blob) {
    FakeXhr.sent.push({ ...this.request, body });
    queueMicrotask(() => {
      const total = body.size;
      this.upload.onprogress?.({
        lengthComputable: true,
        loaded: total / 2,
        total,
      } as ProgressEvent);
      this.upload.onprogress?.({ lengthComputable: true, loaded: total, total } as ProgressEvent);
      this.status = FakeXhr.status;
      this.onload?.();
    });
  }
}

/** A submission as the API answers it, with the given fields changed. */
export function item(over: Partial<Item> = {}): Item {
  return {
    submissionId: "s-1",
    submitter: "me-1",
    submitterIsCurator: false,
    status: "in-review",
    createdAt: "2026-11-10T14:00:00Z",
    round: 1,
    files: { "1": [] },
    datasetId: "stream-temperature-sample",
    newVersion: false,
    rule: null,
    approvals: [],
    stale: false,
    reportKey: "reports/s-1/1.json",
    waiting: true,
    ...over,
  };
}

export function event(type: SubmissionEvent["type"], over: Partial<SubmissionEvent> = {}) {
  return {
    submissionId: "s-1",
    eventKey: `2026-11-10T15:00:0${Math.floor(Math.random() * 10)}Z#${type}`,
    type,
    actor: "pipeline",
    round: 1,
    at: "2026-11-10T15:00:00Z",
    ...over,
  } as SubmissionEvent;
}

export const REPORT: FindingsReport = {
  round: 1,
  validation: { valid: true, contractVersion: "1.4.0", checkedAt: "2026-11-10T15:00:00Z" },
  quality: {
    errors: 1,
    warnings: 1,
    notes: 1,
    auditedAt: "2026-11-10T15:00:00Z",
    score: 87,
    find: { passed: 3, applicable: 4 },
    understand: { passed: 5, applicable: 6 },
    trust: { passed: 2, applicable: 3 },
  },
  findings: [
    {
      ruleId: "understand.units",
      severity: "warning",
      message: "Column water_temp has no unit.",
      target: { resource: "logger", field: "water_temp", path: null },
      evidence: null,
      suggestedFix: "Set the field's unit to degC.",
    },
    {
      ruleId: "trust.methods",
      severity: "note",
      message: "The methods document doesn't name the logger.",
      target: { resource: null, field: null, path: "docs/methods.md" },
      evidence: null,
      suggestedFix: null,
    },
    {
      ruleId: "contract.schema",
      severity: "error",
      message: "Column site_id has values outside its codelist.",
      target: { resource: "logger", field: "site_id", path: null },
      evidence: { rows: [14, 98], values: ["S9", "S0"], count: 2 },
      suggestedFix: "Add S9 and S0 to the site codes.",
    },
  ],
} as FindingsReport;
