import { apiToken } from "./auth";
import type { components } from "./generated/api";

type Schemas = components["schemas"];
export type CatalogRow = Schemas["CatalogRow"];
export type SearchAnswer = Schemas["SearchAnswer"];
export type DatasetAnswer = Schemas["DatasetAnswer"];
export type VersionAnswer = Schemas["VersionAnswer"];
export type VersionsAnswer = Schemas["VersionsAnswer"];

/** The API couldn't be reached, or failed on its side: the reader can only try again. */
export class ApiUnreachable extends Error {
  constructor(cause?: unknown) {
    super("the archive's API can't be reached", { cause });
    this.name = "ApiUnreachable";
  }
}

/**
 * The API answered with a refusal, such as 404 for a dataset that isn't there; `reason` is the
 * API's own words (its `{"error": ...}`) when it gave them.
 */
export class ApiRefused extends Error {
  constructor(
    readonly status: number,
    readonly reason: string | null = null,
  ) {
    super(reason ?? `the archive's API answered ${status}`);
    this.name = "ApiRefused";
  }
}

/** The `error` of a refusal's JSON body, if it has one. */
async function reasonOf(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { error?: unknown };
    return typeof body.error === "string" ? body.error : null;
  } catch {
    return null;
  }
}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    throw new ApiUnreachable(error);
  }
  if (response.status >= 500) throw new ApiUnreachable(response.status);
  if (!response.ok) throw new ApiRefused(response.status);
  return (await response.json()) as T;
}

const segment = encodeURIComponent;

/** `GET /api/search` with the query string as the search page holds it. */
export function search(query: URLSearchParams): Promise<SearchAnswer> {
  return getJson(`/api/search?${query}`);
}

export function getDataset(id: string): Promise<DatasetAnswer> {
  return getJson(`/api/datasets/${segment(id)}`);
}

export function getVersion(id: string, version: number): Promise<VersionAnswer> {
  return getJson(`/api/datasets/${segment(id)}/versions/${version}`);
}

export function getVersions(id: string): Promise<VersionsAnswer> {
  return getJson(`/api/datasets/${segment(id)}/versions`);
}

export type UsageAnswers = Schemas["UsageAnswers"];

/** `POST /api/datasets/{id}/usage`: the reader's optional answers, anonymously. */
export async function sendUsage(id: string, answers: UsageAnswers): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/datasets/${segment(id)}/usage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(answers),
    });
  } catch (error) {
    throw new ApiUnreachable(error);
  }
  if (response.status >= 500) throw new ApiUnreachable(response.status);
  if (!response.ok) throw new ApiRefused(response.status);
}

/**
 * `GET /api/datasets/{id}/versions/{version}/download` with the reader's access token: the
 * short-lived link to one file. 401 means sign in again, 403 the account can't have it.
 */
export async function downloadLink(
  id: string,
  version: number,
  path: string,
  token: string,
): Promise<string> {
  const query = new URLSearchParams({ path });
  const answer = await getJson<Schemas["DownloadAnswer"]>(
    `/api/datasets/${segment(id)}/versions/${version}/download?${query}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  return answer.url;
}

export type Submission = Schemas["Submission"];
export type SubmissionRead = Schemas["SubmissionRead"];
export type SubmissionEvent = Schemas["Event"];
export type SubmittedFile = Schemas["SubmittedFile"];
export type UploadsAnswer = Schemas["UploadsAnswer"];
export type Upload = Schemas["Upload"];
export type HeldFiles = Schemas["HeldFiles"];
export type HeldFile = Schemas["HeldFile"];
export type FindingsReport = Schemas["FindingsReport"];
export type Finding = Schemas["Finding"];
export type ReviewPolicy = Schemas["ReviewPolicy"];
export type Rule = Schemas["Rule"];
export type Curator = Schemas["Curator"];
export type Decision = Schemas["DecisionRequest"]["decision"];

/**
 * A call to a signed-in route with the reader's ID token: 401 without asking when no one is
 * signed in, and the API's own words on any other refusal.
 */
async function signedIn<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const token = apiToken();
  if (!token) throw new ApiRefused(401);
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    throw new ApiUnreachable(error);
  }
  if (response.status >= 500) throw new ApiUnreachable(response.status);
  if (!response.ok) throw new ApiRefused(response.status, await reasonOf(response));
  return (await response.json()) as T;
}

/** `GET /api/submissions`: the reader's own (`mine`), or a curator's list for one status. */
export function listSubmissions(
  query: { mine: true } | { status: Submission["status"] },
): Promise<Schemas["SubmissionList"]> {
  const params = "mine" in query ? "mine=1" : `status=${segment(query.status)}`;
  return signedIn(`/api/submissions?${params}`);
}

export function getSubmission(id: string): Promise<SubmissionRead> {
  return signedIn(`/api/submissions/${segment(id)}`);
}

/** `POST /api/submissions`: round 1's files, answered with their upload links. */
export function createSubmission(
  files: SubmittedFile[],
  datasetId: string,
): Promise<UploadsAnswer> {
  return signedIn("/api/submissions", "POST", { files, datasetId });
}

/** `POST /api/submissions/{id}/uploads`: the next round's links, or new links for a draft. */
export function renewUploads(id: string, files: SubmittedFile[]): Promise<UploadsAnswer> {
  return signedIn(`/api/submissions/${segment(id)}/uploads`, "POST", { files });
}

export function submitRound(id: string): Promise<Schemas["SubmitAnswer"]> {
  return signedIn(`/api/submissions/${segment(id)}/submit`, "POST");
}

export function decide(
  id: string,
  decision: Decision,
  note?: string,
): Promise<Schemas["DecisionAnswer"]> {
  const body = note ? { decision, note } : { decision };
  return signedIn(`/api/submissions/${segment(id)}/decision`, "POST", body);
}

export function heldFiles(id: string): Promise<HeldFiles> {
  return signedIn(`/api/submissions/${segment(id)}/files`);
}

export function getPolicy(): Promise<ReviewPolicy> {
  return signedIn("/api/submissions/policy");
}

export function savePolicy(policy: ReviewPolicy): Promise<ReviewPolicy> {
  return signedIn("/api/submissions/policy", "PUT", policy);
}

/** `GET /api/people`: the emails of up to 50 ids; unknown ids are left out. */
export function lookupPeople(subs: string[]): Promise<Schemas["People"]> {
  const query = new URLSearchParams(subs.map((sub) => ["sub", sub]));
  return signedIn(`/api/people?${query}`);
}

export function listCurators(): Promise<Curator[]> {
  return signedIn("/api/curators");
}
