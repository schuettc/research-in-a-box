/** Words for the tokens the catalog holds: access levels, licence ids, formats and sizes. */

const ACCESS: Record<string, string> = {
  open: "Open",
  restricted: "Restricted",
  "by-request": "By request",
  "description-only": "Description only",
};

/** An access level as an entry's label: "Open", "Restricted". */
export function accessLabel(access: string): string {
  return ACCESS[access] ?? access;
}

/** An access level as a filter: "Open access", "Restricted". */
export function accessFacetLabel(access: string): string {
  return access === "open" ? "Open access" : accessLabel(access);
}

/** The class that colours an access label: green open, amber restricted, grey the rest. */
export function accessClass(access: string): string {
  if (access === "open") return "access open";
  if (access === "restricted" || access === "by-request") return "access restricted";
  return "access";
}

/** A licence id in words: "CC-BY-4.0" reads "CC BY 4.0"; an id it doesn't know reads as itself. */
export function licenceLabel(id: string): string {
  const cc = /^CC-(BY(?:-[A-Z]{2})*)-(\d\.\d)$/.exec(id);
  if (cc) return `CC ${cc[1]} ${cc[2]}`;
  const zero = /^CC0-(\d\.\d)$/.exec(id);
  if (zero) return `CC0 ${zero[1]}`;
  return id;
}

const FORMATS: Record<string, string> = {
  csv: "CSV",
  tsv: "TSV",
  xlsx: "Excel workbook",
  xls: "Excel workbook",
  parquet: "Parquet",
  json: "JSON",
  shp: "Shapefile",
  geojson: "GeoJSON",
  gpkg: "GeoPackage",
  kml: "KML",
  asc: "Esri ASCII grid",
  tif: "GeoTIFF",
  tiff: "GeoTIFF",
  nc: "NetCDF",
  md: "Markdown",
  pdf: "PDF",
  txt: "Text",
  docx: "Word document",
  html: "Web page",
  png: "PNG image",
  jpg: "JPEG image",
  jpeg: "JPEG image",
  gif: "GIF image",
  svg: "SVG image",
  zip: "Zip archive",
};

/** A format as a filter: "Shapefile (.shp)"; one it doesn't know reads as its extension. */
export function formatLabel(format: string): string {
  const name = FORMATS[format.toLowerCase()];
  return name ? `${name} (.${format})` : `.${format}`;
}

const KINDS: [string, string[]][] = [
  ["tables", ["csv", "tsv", "xlsx", "xls", "parquet", "json"]],
  [
    "GIS",
    ["shp", "shx", "dbf", "prj", "cpg", "geojson", "gpkg", "kml", "asc", "tif", "tiff", "nc"],
  ],
  ["documents", ["md", "pdf", "txt", "docx", "html"]],
  ["images", ["png", "jpg", "jpeg", "gif", "svg"]],
];

/** The kinds of file the formats make: tables, GIS, documents, images, other files. */
export function kindsOf(formats: string[]): string[] {
  const lower = formats.map((format) => format.toLowerCase());
  const kinds = KINDS.filter(([, members]) => lower.some((f) => members.includes(f))).map(
    ([kind]) => kind,
  );
  const known = KINDS.flatMap(([, members]) => members);
  if (lower.some((format) => !known.includes(format))) kinds.push("other files");
  return kinds;
}

/** A size in decimal units: "697 B", "50.0 kB". */
export function formatSize(bytes: number): string {
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

/** The submission lifecycle's statuses and audit events, as the API names them. */
export const STATUSES = [
  "draft",
  "checking",
  "needs-changes",
  "in-review",
  "publishing",
  "published",
  "rejected",
  "abandoned",
  "expired",
  "failed",
] as const;
export type Status = (typeof STATUSES)[number];

export const EVENT_TYPES = [
  "created",
  "submitted",
  "scanned",
  "checked",
  "held",
  "entered-review",
  "reminded",
  "stale",
  "decided",
  "resubmitted",
  "published",
  "rejected",
  "abandoned",
  "expired",
  "failed",
] as const;
export type EventType = (typeof EVENT_TYPES)[number];

/** The statuses nothing moves on from. */
export const FINAL_STATUSES: readonly Status[] = [
  "published",
  "rejected",
  "abandoned",
  "expired",
  "failed",
];

const STATUS_LABELS: Record<Status, string> = {
  draft: "Draft",
  checking: "Being checked",
  "needs-changes": "Changes requested",
  "in-review": "In review",
  publishing: "Publishing",
  published: "Published",
  rejected: "Rejected",
  abandoned: "Abandoned",
  expired: "Expired",
  failed: "Failed",
};

/** A status as a short label: "In review", "Changes requested". */
export function statusLabel(status: Status): string {
  return STATUS_LABELS[status] ?? status;
}

const STATUS_LINES: Record<Status, string> = {
  draft: "Not submitted yet: every file needs uploading, then submitting",
  checking: "Checking the files",
  "needs-changes": "Changes requested",
  "in-review": "Waiting for a curator",
  publishing: "Approved, publishing now",
  published: "Published",
  rejected: "Rejected",
  abandoned: "Abandoned: no resubmission came within 30 days",
  expired: "Expired: the submission was kept a year and closed",
  failed: "Stopped by a fault on the archive's side",
};

/** Where a submission stands, as one line for its page. */
export function statusLine(status: Status): string {
  return STATUS_LINES[status] ?? status;
}

const EVENT_LABELS: Record<EventType, string> = {
  created: "Created",
  submitted: "Submitted",
  scanned: "Scanned for malware",
  checked: "Checked",
  held: "Held for review",
  "entered-review": "Entered review",
  reminded: "Curators reminded",
  stale: "Marked stale",
  decided: "Decided",
  resubmitted: "Resubmitted",
  published: "Published",
  rejected: "Rejected",
  abandoned: "Abandoned",
  expired: "Expired",
  failed: "Failed",
};

/** An audit event's type in words. */
export function eventLabel(type: EventType): string {
  return EVENT_LABELS[type] ?? type;
}

const DECISION_LABELS: Record<string, string> = {
  approve: "Approved",
  reject: "Rejected",
  "request-changes": "Changes requested",
};

/** A curator's decision in words: "Approved", "Changes requested". */
export function decisionLabel(decision: string): string {
  return DECISION_LABELS[decision] ?? decision;
}
