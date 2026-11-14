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

/** The API answered with a refusal, such as 404 for a dataset that isn't there. */
export class ApiRefused extends Error {
  constructor(readonly status: number) {
    super(`the archive's API answered ${status}`);
    this.name = "ApiRefused";
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
