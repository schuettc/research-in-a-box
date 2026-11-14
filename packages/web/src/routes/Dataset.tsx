import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import {
  ApiRefused,
  downloadLink,
  getDataset,
  getVersion,
  getVersions,
  type VersionsAnswer,
} from "../api";
import { apiToken, signIn } from "../auth";
import { citation, creatorNames } from "../citation";
import { Coverage } from "../Coverage";
import type { Field, Manifest, Resource, TableSchema } from "../generated/manifest";
import { accessClass, accessLabel, formatSize, kindsOf, licenceLabel } from "../labels";
import { PageHeading, useTitle } from "../page";
import { BRAND } from "../site";
import { UsagePanel, usagePanelDone } from "../UsagePanel";

/** Called once the page has the dataset, so a static dataset page's content can give way. */
export const ShownContext = createContext<() => void>(() => {});

type VersionEntry = VersionsAnswer["versions"][number];

interface View {
  version: number;
  manifest: Manifest;
  access: string;
  project: string | null;
  published: string | null;
  newer: number | null;
  /** Every version, oldest first; null when the list couldn't be had. */
  versions: VersionEntry[] | null;
}

/** The dataset is there but not this version: the page links to the current one. */
class NoSuchVersion extends Error {}

const byVersion = (a: VersionEntry, b: VersionEntry) => a.version - b.version;

async function load(id: string, version: number | undefined): Promise<View> {
  if (version === undefined) {
    const [answer, versions] = await Promise.all([
      getDataset(id),
      getVersions(id).catch(() => null),
    ]);
    const manifest = answer.manifest as Manifest;
    const list = versions?.versions.toSorted(byVersion) ?? null;
    const entry = list?.find((v) => v.version === answer.currentVersion);
    return {
      version: answer.currentVersion,
      manifest,
      access: answer.access,
      project: answer.project ?? manifest["archive:project"] ?? null,
      published: entry?.publishedAt ?? manifest["archive:published"] ?? null,
      newer: null,
      versions: list,
    };
  }
  let answer, versions;
  try {
    [answer, versions] = await Promise.all([getVersion(id, version), getVersions(id)]);
  } catch (error) {
    // Only a 404 says the version isn't there; any other refusal is a failure to try again.
    if (
      error instanceof ApiRefused &&
      error.status === 404 &&
      (await getDataset(id).then(
        () => true,
        () => false,
      ))
    ) {
      throw new NoSuchVersion();
    }
    throw error;
  }
  const manifest = answer.manifest as Manifest;
  const latest = Math.max(...versions.versions.map((entry) => entry.version));
  // Where the files are stored decides open or restricted; the manifest only tells
  // by-request and description-only apart, and a manifest that doesn't say is open.
  const said = manifest["archive:access"];
  const access =
    answer.prefix.split("/")[0] === "restricted"
      ? said && said !== "open"
        ? said
        : "restricted"
      : "open";
  return {
    version: answer.version,
    manifest,
    access,
    project: manifest["archive:project"] ?? null,
    published: answer.publishedAt ?? manifest["archive:published"] ?? null,
    newer: latest > answer.version ? latest : null,
    versions: versions.versions.toSorted(byVersion),
  };
}

type Loaded = { key: string } & (
  { view: View } | { failed: "missing" | "no-version" | "unreachable" }
);

function kindOf(resource: Resource): string {
  return resource["archive:kind"] ?? (resource.type === "table" ? "table" : "file");
}

/** Every file of a resource, with its size when known, its main file first. */
function filesOf(resource: Resource): { path: string; bytes: number | null }[] {
  const members = resource["archive:files"];
  if (members?.length) {
    return members.map((file) => ({ path: file.path, bytes: file.bytes ?? null }));
  }
  const paths = Array.isArray(resource.path) ? resource.path : [resource.path];
  return paths
    .filter((path): path is string => typeof path === "string")
    .map((path) => ({ path, bytes: paths.length === 1 ? (resource.bytes ?? null) : null }));
}

function bytesOf(resource: Resource): number | null {
  if (typeof resource.bytes === "number") return resource.bytes;
  const sizes = resource["archive:files"]?.map((file) => file.bytes);
  if (!sizes?.length || sizes.some((size) => typeof size !== "number")) return null;
  return (sizes as number[]).reduce((total, size) => total + size, 0);
}

const sized = (bytes: number | null) => (bytes === null ? "" : ` (${formatSize(bytes)})`);

function temporal(manifest: Manifest): string | null {
  const coverage = manifest["archive:temporalCoverage"];
  if (!coverage) return null;
  let end = coverage.end ?? "an unknown end";
  if (coverage.ongoing) end = "ongoing";
  else if (coverage.end === "unknown") end = "an unknown end";
  return `${coverage.start} to ${end}`;
}

/** What each access level means, for the banner on a dataset that isn't open. */
const ACCESS_MEANS: Record<string, string> = {
  restricted:
    "The files are available to invited accounts. The description and the columns stay public.",
  "by-request":
    "The files are shared on request, with invited accounts. The description and the columns stay public.",
  "description-only": "This archive holds the description of this dataset, not its files.",
};

function AccessBanner({ access }: { access: string }) {
  const location = useLocation();
  const signedIn = apiToken() !== null;
  const label = accessLabel(access);
  return (
    <section className="banner" aria-label={label}>
      <p>
        <span className={accessClass(access)}>{label}</span>{" "}
        {ACCESS_MEANS[access] ?? "The files aren't open to everyone."}
      </p>
      {access !== "description-only" &&
        (signedIn ? (
          <p>You're signed in; you can download these files if your account has access.</p>
        ) : (
          <p>
            Accounts are by invitation; there's no sign-up.
            {BRAND.contact && (
              <>
                {" "}
                To ask for access, write to <a href={`mailto:${BRAND.contact}`}>{BRAND.contact}</a>.
              </>
            )}
          </p>
        ))}
      {access !== "description-only" && !signedIn && (
        <button
          type="button"
          className="primary"
          onClick={() => void signIn(location.pathname + location.search)}
        >
          Sign in
        </button>
      )}
    </section>
  );
}

function codeList(schema: TableSchema, field: Field, tables: Set<string>): ReactNode {
  const key = schema.foreignKeys?.find((fk) => {
    const fields = Array.isArray(fk.fields) ? fk.fields : [fk.fields];
    return fields.length === 1 && fields[0] === field.name && fk.reference.resource;
  });
  const resource = key?.reference.resource;
  if (resource) {
    const target = tables.has(resource) ? `columns-${resource}` : `file-${resource}`;
    return <a href={`#${target}`}>{resource}</a>;
  }
  if (field["archive:codeList"] === "undocumented") {
    return <span className="missing">No code list</span>;
  }
  return "";
}

/** A description that only repeats the column's name says nothing. */
function described(field: Field): string | null {
  const text = field.description?.trim();
  if (!text || text.toLowerCase() === field.name.toLowerCase()) return null;
  return text;
}

interface FileProps {
  id: string;
  version: number;
  access: string;
  path: string;
  label: string;
  bytes: number | null;
  onDownload: () => void;
  /** The visible words before the label, "Download" unless given. */
  lead?: string;
  /** Visible words after the label, before the size. */
  tail?: string;
}

/** The archive path of the version's zip of every file, and of one multi-file resource's. */
const PACKAGE_ZIP = "_zips/all/package.zip";
const zipOf = (resource: Resource) => `_zips/${resource.name}.zip`;

/** A file of a dataset that isn't open: signed in, its link comes from the API. */
function SignedDownload({
  id,
  version,
  path,
  label,
  bytes,
  onDownload,
  lead = "Download",
  tail = "",
}: Omit<FileProps, "access">) {
  const location = useLocation();
  const [problem, setProblem] = useState<"expired" | "refused" | "failed" | null>(null);
  const token = apiToken();
  const hidden = <span className="visually-hidden">{label}</span>;

  if (problem === "expired") {
    return (
      <span className="file-note">
        Your sign-in has expired.{" "}
        <button
          type="button"
          className="link-button"
          onClick={() => void signIn(location.pathname + location.search)}
        >
          Sign in again {hidden}
        </button>
      </span>
    );
  }
  if (!token) {
    return (
      <span className="file-note locked">
        <span aria-hidden="true">🔒 </span>Sign in above
      </span>
    );
  }
  if (problem === "refused") {
    return <span className="file-note">This file isn't available to this account.</span>;
  }

  async function download(token: string) {
    try {
      const url = await downloadLink(id, version, path, token);
      onDownload();
      window.location.assign(url);
    } catch (error) {
      if (error instanceof ApiRefused && error.status === 401) setProblem("expired");
      else if (error instanceof ApiRefused && error.status === 403) setProblem("refused");
      else setProblem("failed");
    }
  }

  return (
    <>
      <button type="button" className="button download" onClick={() => void download(token)}>
        <span>
          {lead} {hidden}
          {tail}
          {sized(bytes)}
        </span>
      </button>
      {problem === "failed" && (
        <span className="file-note">The download couldn't start. Try again.</span>
      )}
    </>
  );
}

function FileDownload({
  id,
  version,
  access,
  path,
  label,
  bytes,
  onDownload,
  lead = "Download",
  tail = "",
}: FileProps) {
  if (access !== "open") {
    return (
      <SignedDownload
        id={id}
        version={version}
        path={path}
        label={label}
        bytes={bytes}
        onDownload={onDownload}
        lead={lead}
        tail={tail}
      />
    );
  }
  const href = `/data/${encodeURIComponent(id)}/${version}/${path.split("/").map(encodeURIComponent).join("/")}`;
  return (
    <a className="button download" href={href} download onClick={onDownload}>
      <span>
        {lead} <span className="visually-hidden">{label}</span>
        {tail}
        {sized(bytes)}
      </span>
    </a>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <p className="copy-row">
      <button
        type="button"
        onClick={() => navigator.clipboard.writeText(text).then(() => setCopied(true))}
      >
        Copy
      </button>
      <span className="copied" aria-live="polite">
        {copied ? "Copied ✓" : ""}
      </span>
    </p>
  );
}

function Versions({ id, view }: { id: string; view: View }) {
  if (!view.versions?.length) return null;
  return (
    <section className="panel" aria-labelledby="versions-heading">
      <h2 id="versions-heading">Versions</h2>
      <ol className="versions">
        {view.versions.map((entry) => (
          <li key={entry.version}>
            <Link to={`/datasets/${encodeURIComponent(id)}/v${entry.version}`}>
              Version {entry.version}
            </Link>
            {entry.publishedAt && (
              <span className="muted"> · {entry.publishedAt.slice(0, 10)}</span>
            )}
            {entry.version === view.version && <span className="muted"> · cited above</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}

function DatasetPage({ id, view }: { id: string; view: View }) {
  const { manifest } = view;
  const title = manifest.title ?? manifest.name ?? id;
  useTitle(title);
  const [usageFor, setUsageFor] = useState<string | null>(null);
  const downloaded = (resource: string) => () => {
    if (!usagePanelDone()) setUsageFor(resource);
  };
  const cited = citation(
    manifest,
    `${location.origin}/datasets/${encodeURIComponent(id)}/v${view.version}`,
  );
  const licences = (manifest.licenses ?? []).map((l) =>
    licenceLabel(l.name ?? l.title ?? l.path ?? ""),
  );
  const rights = manifest["archive:rightsStatus"];
  const creators = creatorNames(manifest);
  const resources = manifest.resources ?? [];
  const tables = resources.filter((r) => kindOf(r) === "table" && r.schema?.fields?.length);
  const tableNames = new Set(tables.map((r) => r.name));
  const stored = resources.filter((r) => kindOf(r) !== "linked");
  const storedFiles = stored.flatMap(filesOf);
  const sizes = stored.map(bytesOf);
  const total = sizes.every((size) => size !== null)
    ? (sizes as number[]).reduce((sum, size) => sum + size, 0)
    : null;
  const kinds = kindsOf(storedFiles.map((file) => file.path.split(".").pop() ?? ""));
  const when = temporal(manifest);
  const spatial = manifest["archive:spatialCoverage"];

  const meta = [
    creators.join(", "),
    view.published ? `Published ${view.published.slice(0, 10)}` : "",
    `Version ${view.version}`,
    licences.join(", ") || (rights ? rights.status : ""),
  ].filter(Boolean);
  const summary = [
    `${storedFiles.length} ${storedFiles.length === 1 ? "file" : "files"}`,
    total === null ? "" : formatSize(total),
    kinds.join(", "),
    when ?? "",
  ].filter(Boolean);

  const about: [string, ReactNode][] = [];
  if (creators.length) about.push(["Creators", creators.join(", ")]);
  if (manifest["archive:purpose"]) about.push(["Purpose", manifest["archive:purpose"]]);
  if (manifest["archive:methods"]) about.push(["Methods", manifest["archive:methods"]]);
  const funding = manifest["archive:funding"];
  if (funding?.length) {
    about.push([
      "Funding",
      <ul>
        {funding.map((grant, index) => (
          <li key={index}>
            {grant.funder}
            {grant.awardTitle ? `: ${grant.awardTitle}` : ""}
            {grant.awardNumber ? ` (${grant.awardNumber})` : ""}
          </li>
        ))}
      </ul>,
    ]);
  }
  const related = manifest["archive:relatedIdentifiers"];
  if (related?.length) {
    about.push([
      "Related works",
      <ul>
        {related.map((work, index) => (
          <li key={index}>
            {work.relationType}{" "}
            {/^https?:\/\//.test(work.identifier) ? (
              <a href={work.identifier}>{work.identifier}</a>
            ) : (
              `${work.identifierType} ${work.identifier}`
            )}
          </li>
        ))}
      </ul>,
    ]);
  }
  if (manifest.licenses?.length || rights) {
    about.push([
      "Rights",
      <ul>
        {(manifest.licenses ?? []).map((l, index) => {
          const label = l.name ?? l.title ?? l.path ?? "";
          return (
            <li key={index}>
              Licensed {licenceLabel(label)}
              {l.title && l.name ? ` (${l.title})` : ""}
              {l.path && l.path !== label && (
                <>
                  : <a href={l.path}>{l.path}</a>
                </>
              )}
            </li>
          );
        })}
        {rights && (
          <li>
            Rights status {rights.status}
            {rights.statement ? `: ${rights.statement}` : ""}
          </li>
        )}
      </ul>,
    ]);
  }
  if (view.project) about.push(["Project", view.project]);
  if (manifest.keywords?.length) about.push(["Keywords", manifest.keywords.join(", ")]);
  if (when) about.push(["Temporal coverage", when]);
  if (spatial) about.push(["Spatial coverage", <Coverage coverage={spatial} />]);

  return (
    <article className="dataset">
      {usageFor && <UsagePanel datasetId={id} onClose={() => setUsageFor(null)} />}
      <div className="ds-grid">
        <div className="ds-main">
          <PageHeading>{title}</PageHeading>
          <p className="ds-meta" data-testid="meta">
            {meta.join(" · ")}
          </p>
          {view.newer !== null && (
            <p className="note">
              A newer version of this dataset exists:{" "}
              <Link to={`/datasets/${encodeURIComponent(id)}/v${view.newer}`}>
                version {view.newer}
              </Link>
              .
            </p>
          )}
          {view.access !== "open" && <AccessBanner access={view.access} />}
          {manifest.description && <p className="lede">{manifest.description}</p>}
          <div className="summary-strip" data-testid="summary-strip">
            <p className="summary" data-testid="summary">
              {summary.join(" · ")}
            </p>
            {storedFiles.length > 0 && view.access !== "description-only" && (
              <FileDownload
                id={id}
                version={view.version}
                access={view.access}
                path={PACKAGE_ZIP}
                label="every file as one zip"
                bytes={null}
                lead="Download all"
                onDownload={downloaded(PACKAGE_ZIP)}
              />
            )}
          </div>

          <section className="block" aria-labelledby="files-heading">
            <h2 id="files-heading">Files</h2>
            <ul className="files" aria-labelledby="files-heading">
              {resources.map((resource) => {
                const label = resource.title ?? resource.name;
                const kind = kindOf(resource);
                const files = filesOf(resource);
                const main = files[0];
                const fileProps = {
                  id,
                  version: view.version,
                  access: view.access,
                  onDownload: downloaded(resource.name),
                };
                return (
                  <li key={resource.name} id={`file-${resource.name}`} className="file">
                    <p className="file-head">
                      <span className="file-title">{label}</span>{" "}
                      <span className="label">{kind}</span>
                    </p>
                    <div className="file-action">
                      {kind === "linked" && typeof resource.path === "string" ? (
                        <a className="button download" href={resource.path}>
                          Open link <span className="visually-hidden">{label}</span>
                        </a>
                      ) : (
                        main &&
                        (files.length > 1 ? (
                          <FileDownload
                            {...fileProps}
                            path={zipOf(resource)}
                            label={label}
                            bytes={null}
                            tail=" as a zip"
                          />
                        ) : (
                          <FileDownload
                            {...fileProps}
                            path={main.path}
                            label={label}
                            bytes={bytesOf(resource)}
                          />
                        ))
                      )}
                    </div>
                    {resource.description && <p className="file-about">{resource.description}</p>}
                    {kind === "linked" ? (
                      <p className="file-path muted">External</p>
                    ) : (
                      main && <code className="file-path">{main.path}</code>
                    )}
                    {files.length > 1 && (
                      <details className="members">
                        <summary>Files in this set ({files.length})</summary>
                        <ul>
                          {files.map((file) => (
                            <li key={file.path}>
                              <code>{file.path}</code>{" "}
                              <FileDownload
                                {...fileProps}
                                path={file.path}
                                label={file.path}
                                bytes={file.bytes}
                              />
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>

          {tables.length > 0 && (
            <section className="block" aria-labelledby="columns-heading">
              <h2 id="columns-heading">Columns</h2>
              {tables.map((resource) => {
                const schema = resource.schema as TableSchema;
                const label = resource.title ?? resource.name;
                const fields = schema.fields ?? [];
                return (
                  <details key={resource.name} id={`columns-${resource.name}`} open>
                    <summary>
                      <h3>{label}</h3>{" "}
                      <span className="muted">
                        {fields.length} {fields.length === 1 ? "column" : "columns"}
                      </span>
                    </summary>
                    <div
                      className="table-scroll"
                      role="region"
                      aria-label={`Columns of ${label}, scrolls sideways`}
                      tabIndex={0}
                    >
                      <table className="cols" aria-label={`Columns of ${label}`}>
                        <thead>
                          <tr>
                            <th scope="col">Column</th>
                            <th scope="col">Title</th>
                            <th scope="col">Type</th>
                            <th scope="col">Unit</th>
                            <th scope="col">Description</th>
                            <th scope="col">Codes</th>
                          </tr>
                        </thead>
                        <tbody>
                          {fields.map((field) => (
                            <tr key={field.name}>
                              <th scope="row">
                                <code>{field.name}</code>
                              </th>
                              <td>{field.title ?? ""}</td>
                              <td>{field.type ?? ""}</td>
                              <td>{field["archive:unit"] ?? ""}</td>
                              <td>
                                {described(field) ?? (
                                  <span className="missing">No description</span>
                                )}
                              </td>
                              <td>{codeList(schema, field, tableNames)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                );
              })}
            </section>
          )}

          {about.length > 0 && (
            <section className="block" aria-labelledby="about-heading">
              <h2 id="about-heading">About</h2>
              <dl className="facts">
                {about.map(([term, detail]) => (
                  <div key={term}>
                    <dt>{term}</dt>
                    <dd>{detail}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
        </div>

        <aside className="ds-side" aria-label="Cite and versions">
          {cited && (
            <section className="panel" aria-labelledby="cite-heading">
              <h2 id="cite-heading">Cite this dataset</h2>
              <div className="citation">
                <p>{cited}</p>
                <CopyButton text={cited} />
              </div>
            </section>
          )}
          <Versions id={id} view={view} />
        </aside>
      </div>
    </article>
  );
}

function Title({ page }: { page: string }) {
  useTitle(page);
  return null;
}

function Loading() {
  useTitle("Loading dataset");
  return (
    <>
      <PageHeading>Loading dataset…</PageHeading>
      <p role="status" className="muted">
        One moment.
      </p>
    </>
  );
}

export function Dataset({ id, version }: { id: string; version?: number }) {
  const [attempt, setAttempt] = useState(0);
  const key = `${id}@${version ?? "current"}#${attempt}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const shown = useContext(ShownContext);

  useEffect(() => {
    let current = true;
    load(id, version).then(
      (view) => current && setLoaded({ key, view }),
      (error: unknown) => {
        const failed =
          error instanceof NoSuchVersion
            ? "no-version"
            : error instanceof ApiRefused && error.status === 404
              ? "missing"
              : "unreachable";
        if (current) setLoaded({ key, failed });
      },
    );
    return () => {
      current = false;
    };
  }, [id, version, key]);

  const result = loaded?.key === key ? loaded : null;
  const view = result && "view" in result ? result.view : null;
  useEffect(() => {
    if (view) shown();
  }, [view, shown]);

  const current = `/datasets/${encodeURIComponent(id)}`;
  if (!result) return <Loading />;
  if ("failed" in result) {
    if (result.failed === "missing") {
      return (
        <>
          <Title page="Not found" />
          <PageHeading>Dataset not found</PageHeading>
          <p>
            There's no dataset {id}. <Link to="/">Search the archive</Link>.
          </p>
        </>
      );
    }
    if (result.failed === "no-version") {
      return (
        <>
          <Title page="Not found" />
          <PageHeading>Version not found</PageHeading>
          <p>
            Dataset {id} has no version {version}. <Link to={current}>See the current version</Link>{" "}
            or <Link to="/">search the archive</Link>.
          </p>
        </>
      );
    }
    return (
      <>
        <Title page="Dataset unavailable" />
        <PageHeading>Dataset unavailable</PageHeading>
        <p role="alert">This dataset can't be loaded right now.</p>
        <p className="actions">
          <button type="button" className="primary" onClick={() => setAttempt((n) => n + 1)}>
            Try again
          </button>
          <Link className="button" to="/">
            Search the archive
          </Link>
        </p>
        <p>
          The dataset's current version has a page that reads without the archive's search:{" "}
          {/* A full page load, so the static page answers even with the API down. */}
          <a href={current}>{id}, current version</a>.
          {BRAND.contact && (
            <>
              {" "}
              If this keeps happening, contact{" "}
              <a href={`mailto:${BRAND.contact}`}>{BRAND.contact}</a>.
            </>
          )}
        </p>
      </>
    );
  }
  return <DatasetPage id={id} view={result.view} />;
}
