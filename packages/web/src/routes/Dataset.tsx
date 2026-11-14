import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router";
import { ApiRefused, downloadLink, getDataset, getVersion, getVersions } from "../api";
import { accessToken, signIn } from "../auth";
import { citation, creatorNames } from "../citation";
import type { Field, Manifest, Resource, TableSchema } from "../generated/manifest";
import { UsagePanel, usagePanelDone } from "../UsagePanel";

/** Called once the page has the dataset, so a static dataset page's content can give way. */
export const ShownContext = createContext<() => void>(() => {});

interface View {
  version: number;
  manifest: Manifest;
  access: string;
  project: string | null;
  published: string | null;
  newer: number | null;
}

async function load(id: string, version: number | undefined): Promise<View> {
  if (version === undefined) {
    const answer = await getDataset(id);
    const manifest = answer.manifest as Manifest;
    return {
      version: answer.currentVersion,
      manifest,
      access: answer.access,
      project: answer.project ?? manifest["archive:project"] ?? null,
      published: manifest["archive:published"] ?? null,
      newer: null,
    };
  }
  const [answer, versions] = await Promise.all([getVersion(id, version), getVersions(id)]);
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
  };
}

type Loaded = { key: string } & ({ view: View } | { failed: "missing" | "unreachable" });

function kindOf(resource: Resource): string {
  return resource["archive:kind"] ?? (resource.type === "table" ? "table" : "file");
}

/** Every file of a resource, its main file first. */
function filesOf(resource: Resource): string[] {
  const members = resource["archive:files"]?.map((file) => file.path);
  if (members?.length) return members;
  if (Array.isArray(resource.path)) return resource.path;
  return typeof resource.path === "string" ? [resource.path] : [];
}

function bytesOf(resource: Resource): number | null {
  if (typeof resource.bytes === "number") return resource.bytes;
  const sizes = resource["archive:files"]?.map((file) => file.bytes);
  if (!sizes?.length || sizes.some((size) => typeof size !== "number")) return null;
  return (sizes as number[]).reduce((total, size) => total + size, 0);
}

function formatSize(bytes: number | null): string {
  if (bytes === null) return "";
  if (bytes < 1000) return `${bytes} B`;
  const units = ["kB", "MB", "GB", "TB"];
  let value = bytes / 1000;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

function temporal(manifest: Manifest): string | null {
  const coverage = manifest["archive:temporalCoverage"];
  if (!coverage) return null;
  let end = coverage.end ?? "an unknown end";
  if (coverage.ongoing) end = "ongoing";
  else if (coverage.end === "unknown") end = "an unknown end";
  return `${coverage.start} to ${end}`;
}

function spatial(manifest: Manifest): string | null {
  const coverage = manifest["archive:spatialCoverage"];
  if (!coverage) return null;
  const [west, south, east, north] = coverage.bbox.map(String);
  const place = coverage.description ? `. ${coverage.description}` : "";
  return `west ${west}, south ${south}, east ${east}, north ${north}${place}`;
}

function codesOf(schema: TableSchema, field: Field): string {
  const key = schema.foreignKeys?.find((fk) => {
    const fields = Array.isArray(fk.fields) ? fk.fields : [fk.fields];
    return fields.length === 1 && fields[0] === field.name && fk.reference.resource;
  });
  if (key?.reference.resource) return key.reference.resource;
  return field["archive:codeList"] === "undocumented" ? "undocumented" : "";
}

interface FileProps {
  id: string;
  version: number;
  access: string;
  path: string;
  label: string;
  onDownload: () => void;
}

/** A file of a dataset that isn't open: signed in, its link comes from the API. */
function SignedDownload({ id, version, path, label, onDownload }: Omit<FileProps, "access">) {
  const location = useLocation();
  const [problem, setProblem] = useState<"expired" | "refused" | "failed" | null>(null);
  const token = accessToken();
  const hidden = <span className="visually-hidden">{label}</span>;

  if (!token || problem === "expired") {
    return (
      <>
        {problem === "expired" && <span>Your sign-in has expired.</span>}{" "}
        <button type="button" onClick={() => void signIn(location.pathname + location.search)}>
          Sign in to download {hidden}
        </button>
      </>
    );
  }
  if (problem === "refused") return <span>This file isn't available to this account.</span>;

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
      <button type="button" onClick={() => void download(token)}>
        Download {hidden}
      </button>
      {problem === "failed" && <span> The download couldn't start. Try again.</span>}
    </>
  );
}

function FileDownload({ id, version, access, path, label, onDownload }: FileProps) {
  if (access !== "open") {
    return (
      <SignedDownload id={id} version={version} path={path} label={label} onDownload={onDownload} />
    );
  }
  const href = `/data/${encodeURIComponent(id)}/${version}/${path.split("/").map(encodeURIComponent).join("/")}`;
  return (
    <a href={href} download onClick={onDownload}>
      Download <span className="visually-hidden">{label}</span>
    </a>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => navigator.clipboard.writeText(text).then(() => setCopied(true))}
      >
        Copy
      </button>
      <span aria-live="polite">{copied ? " Copied" : ""}</span>
    </>
  );
}

function DatasetPage({ id, view }: { id: string; view: View }) {
  const { manifest } = view;
  const title = manifest.title ?? manifest.name ?? id;
  const [usageOpen, setUsageOpen] = useState(false);
  const onDownload = () => {
    if (!usagePanelDone()) setUsageOpen(true);
  };
  const cited = citation(
    manifest,
    `${location.origin}/datasets/${encodeURIComponent(id)}/v${view.version}`,
  );
  const licences = (manifest.licenses ?? []).map((l) => l.name ?? l.title ?? l.path ?? "");
  const rights = manifest["archive:rightsStatus"];
  const creators = creatorNames(manifest);
  const resources = manifest.resources ?? [];
  const tables = resources.filter((r) => kindOf(r) === "table" && r.schema?.fields?.length);
  const about: [string, ReactNode][] = [];
  if (creators.length) about.push(["Creators", creators.join(", ")]);
  if (manifest["archive:purpose"]) about.push(["Purpose", manifest["archive:purpose"]]);
  if (manifest.licenses?.length || rights) {
    about.push([
      "Rights",
      <ul>
        {(manifest.licenses ?? []).map((l, index) => {
          const label = l.name ?? l.title ?? l.path ?? "";
          return (
            <li key={index}>
              Licensed {label}
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
  const when = temporal(manifest);
  if (when) about.push(["Temporal coverage", when]);
  const where = spatial(manifest);
  if (where) about.push(["Spatial coverage", where]);

  return (
    <article className="dataset">
      <h1>{title}</h1>
      {view.newer !== null && (
        <p className="note">
          A newer version of this dataset exists:{" "}
          <Link to={`/datasets/${encodeURIComponent(id)}/v${view.newer}`}>
            version {view.newer}
          </Link>
          .
        </p>
      )}
      {manifest.description && <p>{manifest.description}</p>}
      <ul className="badges">
        <li>{view.access}</li>
        {licences.length
          ? licences.map((licence) => <li key={licence}>{licence}</li>)
          : rights && <li>{rights.status}</li>}
        {view.published && <li>Published {view.published.slice(0, 10)}</li>}
        <li>Version {view.version}</li>
      </ul>

      {cited && (
        <section aria-labelledby="cite-heading">
          <h2 id="cite-heading">Cite this dataset</h2>
          <p className="citation">{cited}</p>
          <CopyButton text={cited} />
        </section>
      )}

      {about.length > 0 && (
        <section aria-labelledby="about-heading">
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

      <section aria-labelledby="files-heading">
        <h2 id="files-heading">Files</h2>
        <table aria-labelledby="files-heading">
          <thead>
            <tr>
              <th scope="col">Title</th>
              <th scope="col">Kind</th>
              <th scope="col">File</th>
              <th scope="col">Size</th>
              <th scope="col">Download</th>
            </tr>
          </thead>
          <tbody>
            {resources.map((resource) => {
              const label = resource.title ?? resource.name;
              const kind = kindOf(resource);
              const files = filesOf(resource);
              const main = typeof resource.path === "string" ? resource.path : files[0];
              const fileProps = { id, version: view.version, access: view.access, onDownload };
              return (
                <tr key={resource.name}>
                  <td>{label}</td>
                  <td>{kind}</td>
                  <td>
                    {kind !== "linked" && main && <code>{main}</code>}
                    {files.length > 1 && (
                      <>
                        {` (${files.length} files)`}
                        <ul className="members">
                          {files
                            .filter((file) => file !== main)
                            .map((file) => (
                              <li key={file}>
                                <code>{file}</code>{" "}
                                <FileDownload {...fileProps} path={file} label={file} />
                              </li>
                            ))}
                        </ul>
                      </>
                    )}
                  </td>
                  <td>{kind === "linked" ? "" : formatSize(bytesOf(resource))}</td>
                  <td>
                    {kind === "linked" && typeof resource.path === "string" ? (
                      <a href={resource.path}>
                        Open link <span className="visually-hidden">{label}</span>
                      </a>
                    ) : (
                      main && <FileDownload {...fileProps} path={main} label={label} />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {usageOpen && <UsagePanel datasetId={id} onClose={() => setUsageOpen(false)} />}
      </section>

      {tables.length > 0 && (
        <section aria-labelledby="columns-heading">
          <h2 id="columns-heading">Columns</h2>
          {tables.map((resource) => {
            const schema = resource.schema as TableSchema;
            const label = resource.title ?? resource.name;
            return (
              <div key={resource.name}>
                <h3>{label}</h3>
                <table aria-label={`Columns of ${label}`}>
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
                    {(schema.fields ?? []).map((field) => (
                      <tr key={field.name}>
                        <td>
                          <code>{field.name}</code>
                        </td>
                        <td>{field.title ?? ""}</td>
                        <td>{field.type ?? ""}</td>
                        <td>{field["archive:unit"] ?? ""}</td>
                        <td>
                          {field.description ?? <span className="muted">No description</span>}
                        </td>
                        <td>{codesOf(schema, field)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </section>
      )}
    </article>
  );
}

export function Dataset({ id, version }: { id: string; version?: number }) {
  const key = `${id}@${version ?? "current"}`;
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const shown = useContext(ShownContext);

  useEffect(() => {
    let current = true;
    load(id, version).then(
      (view) => current && setLoaded({ key, view }),
      (error: unknown) => {
        const failed = error instanceof ApiRefused ? "missing" : "unreachable";
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

  if (!result) return <p role="status">Loading the dataset…</p>;
  if ("failed" in result) {
    if (result.failed === "missing") {
      return (
        <>
          <h1>Dataset not found</h1>
          <p>
            There's no dataset {id}
            {version ? ` version ${version}` : ""}. <Link to="/">Search the archive</Link>.
          </p>
        </>
      );
    }
    return (
      <>
        <h1>Dataset</h1>
        <p role="alert">This dataset can't be loaded right now.</p>
      </>
    );
  }
  return <DatasetPage id={id} view={result.view} />;
}
