// Generated from the archive contract's JSON Schema by `just web-types`. Do not edit.

export type $Schema = string | null;
export type ArchiveAccess = ("open" | "restricted" | "by-request" | "description-only") | null;
export type ArchiveCitation = string | null;
export type ArchiveFunding = Funding[] | null;
export type Awardnumber = string | null;
export type Awardtitle = string | null;
export type Awarduri = string | null;
export type Funder = string;
export type ArchiveLegacyidentifiers = LegacyIdentifier[] | null;
export type Scheme = string;
export type Value = string;
export type ArchiveMetadatahistory = MetadataEdit[] | null;
export type Fields = string[];
export type When = string;
export type Who = string;
export type ArchiveMethods = string | null;
export type ArchiveProject = string | null;
export type ArchivePublished = string | null;
export type ArchivePurpose = string | null;
export type Auditedat = string;
export type Errors = number;
export type Applicable = number;
export type Passed = number;
export type Notes = number;
export type Score = number | null;
export type Warnings = number;
export type ArchiveRelatedidentifiers = RelatedIdentifier[] | null;
export type Identifier = string;
export type Identifiertype = string;
export type Relationtype = string;
export type Statement = string | null;
export type Status = "public-domain" | "third-party" | "all-rights-reserved" | "undetermined";
/**
 * @minItems 4
 * @maxItems 4
 */
export type Bbox = [unknown, unknown, unknown, unknown];
export type Description = string | null;
export type End = string | "unknown" | null;
export type Ongoing = boolean;
export type Start = string;
export type Checkedat = string;
export type Contractversion = string;
export type Valid = boolean;
export type Contributors = Contributor[] | null;
export type Email = string | null;
export type Familyname = string | null;
export type Givenname = string | null;
export type Organization = string | null;
export type Path = string | null;
export type Roles = string[] | null;
export type Title = string | null;
export type Created = string | null;
export type Description1 = string | null;
export type Homepage = string | null;
export type Id = string | null;
export type Image = string | null;
export type Keywords = string[] | null;
export type Licenses = License[] | null;
export type Name = string | null;
export type Path1 = string | null;
export type Title1 = string | null;
export type Name1 = string | null;
export type ArchiveAlternateof = string | null;
export type Field1 = string;
export type Role = "uncertainty" | "detection-limit" | "quality-flag";
export type ArchiveCodelist = "undocumented" | null;
export type ArchiveMeasurementscale =
  ("nominal" | "ordinal" | "interval" | "ratio" | "dateTime") | null;
export type ArchiveSensitivity = ("personal" | "sensitive-location" | "confidential") | null;
export type ArchiveSourcename = string | null;
export type ArchiveUnit = string | null;
export type Constraints = {
  [k: string]: unknown;
} | null;
export type Description2 = string | null;
export type Format = string | null;
export type Name2 = string;
export type Title2 = string | null;
export type Type =
  | (
      | "string"
      | "number"
      | "integer"
      | "boolean"
      | "object"
      | "array"
      | "list"
      | "datetime"
      | "date"
      | "time"
      | "year"
      | "yearmonth"
      | "duration"
      | "geopoint"
      | "geojson"
      | "any"
    )
  | null;
export type Fields1 = Field[];
export type Foreignkeys = ForeignKey[] | null;
export type Fields2 = string[] | string;
export type Fields3 = string[] | string;
export type Resource1 = string | null;
export type Missingvalues = unknown[] | null;
export type Primarykey = string[] | string | null;
export type ArchiveFiles = MemberFile[] | null;
export type Bytes = number | null;
export type Hash = string | null;
export type Path2 = string;
export type ArchiveKind = "table" | "vector" | "raster" | "document" | "media" | "file" | "linked";
export type Bytes1 = number | null;
export type Description3 = string | null;
export type Dialect = {
  [k: string]: unknown;
} | null;
export type Encoding = string | null;
export type Format1 = string | null;
export type Hash1 = string | null;
export type Licenses1 = License[] | null;
export type Mediatype = string | null;
export type Name3 = string;
export type Path3 = string | string[] | null;
export type Sources =
  | {
      [k: string]: unknown;
    }[]
  | null;
export type Title3 = string | null;
export type Type1 = "table" | null;
export type Resources = Resource[];
export type Sources1 =
  | {
      [k: string]: unknown;
    }[]
  | null;
export type Title4 = string | null;
export type Version = string | null;

/**
 * A package's `datapackage.json`: a Frictionless v2 Data Package with `archive:` additions.
 *
 * The core fields are optional here so a package can be built and audited before it is
 * complete; `missing_core_fields` lists the ones still absent.
 */
export interface Manifest {
  $schema?: $Schema;
  "archive:access"?: ArchiveAccess;
  "archive:citation"?: ArchiveCitation;
  "archive:funding"?: ArchiveFunding;
  "archive:legacyIdentifiers"?: ArchiveLegacyidentifiers;
  "archive:metadataHistory"?: ArchiveMetadatahistory;
  "archive:methods"?: ArchiveMethods;
  "archive:project"?: ArchiveProject;
  "archive:published"?: ArchivePublished;
  "archive:purpose"?: ArchivePurpose;
  "archive:quality"?: QualityVerdict | null;
  "archive:relatedIdentifiers"?: ArchiveRelatedidentifiers;
  "archive:rightsStatus"?: RightsStatus | null;
  "archive:spatialCoverage"?: SpatialCoverage | null;
  "archive:temporalCoverage"?: TemporalCoverage | null;
  "archive:validation"?: ValidationVerdict | null;
  contributors?: Contributors;
  created?: Created;
  description?: Description1;
  homepage?: Homepage;
  id?: Id;
  image?: Image;
  keywords?: Keywords;
  licenses?: Licenses;
  name?: Name1;
  resources?: Resources;
  sources?: Sources1;
  title?: Title4;
  version?: Version;
  [k: string]: unknown;
}
export interface Funding {
  awardNumber?: Awardnumber;
  awardTitle?: Awardtitle;
  awardUri?: Awarduri;
  funder: Funder;
  [k: string]: unknown;
}
/**
 * An identifier the data had elsewhere, such as an EML package id.
 */
export interface LegacyIdentifier {
  scheme: Scheme;
  value: Value;
  [k: string]: unknown;
}
/**
 * One in-place metadata edit of the current version.
 */
export interface MetadataEdit {
  fields: Fields;
  when: When;
  who: Who;
  [k: string]: unknown;
}
/**
 * The counts of findings by severity from the last audit, and the completeness score.
 *
 * `score` is the share of checks passed, as a whole percent rounded down; `find`,
 * `understand` and `trust` count the checks for each of the three questions.
 */
export interface QualityVerdict {
  auditedAt: Auditedat;
  errors: Errors;
  find?: CheckCount | null;
  notes: Notes;
  score?: Score;
  trust?: CheckCount | null;
  understand?: CheckCount | null;
  warnings: Warnings;
  [k: string]: unknown;
}
/**
 * How many of the checks that applied passed.
 */
export interface CheckCount {
  applicable: Applicable;
  passed: Passed;
  [k: string]: unknown;
}
/**
 * A DataCite related identifier, such as a paper the data supplements.
 */
export interface RelatedIdentifier {
  identifier: Identifier;
  identifierType: Identifiertype;
  relationType: Relationtype;
  [k: string]: unknown;
}
/**
 * `archive:rightsStatus`: the rights of a package that has no license.
 *
 * `third-party` needs a statement of where the terms are set, `all-rights-reserved` the
 * rights statement itself.
 */
export interface RightsStatus {
  statement?: Statement;
  status: Status;
  [k: string]: unknown;
}
/**
 * Where the data covers, as a WGS 84 bounding box: west, south, east, north.
 *
 * West may be greater than east for a box that crosses the antimeridian.
 */
export interface SpatialCoverage {
  bbox: Bbox;
  description?: Description;
  [k: string]: unknown;
}
/**
 * When the data covers: a start, and an end date, `end: "unknown"` or `ongoing`.
 *
 * `end: "unknown"` is for data that stopped at a date nobody recorded.
 */
export interface TemporalCoverage {
  end?: End;
  ongoing?: Ongoing;
  start: Start;
  [k: string]: unknown;
}
/**
 * Whether the package is structurally valid, by which contract version, and when.
 */
export interface ValidationVerdict {
  checkedAt: Checkedat;
  contractVersion: Contractversion;
  valid: Valid;
  [k: string]: unknown;
}
/**
 * A Frictionless v2 contributor. A creator is a contributor with the `creator` role.
 */
export interface Contributor {
  email?: Email;
  familyName?: Familyname;
  givenName?: Givenname;
  organization?: Organization;
  path?: Path;
  roles?: Roles;
  title?: Title;
  [k: string]: unknown;
}
/**
 * A Frictionless license: an SPDX id in `name`, a license URL in `path`, or both.
 */
export interface License {
  name?: Name;
  path?: Path1;
  title?: Title1;
  [k: string]: unknown;
}
/**
 * A Frictionless resource with the archive's additions.
 *
 * - `archive:kind` says what the resource is; with none it reads as `table` when `type` is
 *   `table`, and as `file` otherwise. Frictionless's `type` is `table` for a table (written
 *   when absent) and is refused on any other kind.
 * - `archive:files` lists every member file of a multi-file resource (a shapefile set),
 *   with `path` naming the main file.
 * - `archive:alternateOf` names the primary when this is the same data in another format;
 *   only the primary carries the schema.
 * - A `linked` resource is held elsewhere: `path` is its URL and it has no hash or size.
 * - `archive:attributes` describes a `vector` resource's attribute table as a Table Schema.
 */
export interface Resource {
  "archive:alternateOf"?: ArchiveAlternateof;
  "archive:attributes"?: TableSchema | null;
  "archive:files"?: ArchiveFiles;
  "archive:kind"?: ArchiveKind;
  bytes?: Bytes1;
  data?: Data;
  description?: Description3;
  dialect?: Dialect;
  encoding?: Encoding;
  format?: Format1;
  hash?: Hash1;
  licenses?: Licenses1;
  mediatype?: Mediatype;
  name: Name3;
  path?: Path3;
  schema?: TableSchema | null;
  sources?: Sources;
  title?: Title3;
  type?: Type1;
  [k: string]: unknown;
}
/**
 * A Frictionless Table Schema.
 */
export interface TableSchema {
  fields?: Fields1;
  foreignKeys?: Foreignkeys;
  missingValues?: Missingvalues;
  primaryKey?: Primarykey;
  [k: string]: unknown;
}
/**
 * One column of a table, described by logical type rather than file format.
 *
 * `name` is the column's name in the tidy table. When a rename was accepted, the column's
 * name in the source file is kept in `archive:sourceName`. `archive:unit` is free text
 * (`degC`, `mg/L`); `archive:ancillaryOf` names another column of the same schema that
 * this one qualifies.
 */
export interface Field {
  "archive:ancillaryOf"?: AncillaryOf | null;
  "archive:codeList"?: ArchiveCodelist;
  "archive:measurementScale"?: ArchiveMeasurementscale;
  "archive:sensitivity"?: ArchiveSensitivity;
  "archive:sourceName"?: ArchiveSourcename;
  "archive:unit"?: ArchiveUnit;
  constraints?: Constraints;
  description?: Description2;
  example?: Example;
  format?: Format;
  name: Name2;
  title?: Title2;
  type?: Type;
  [k: string]: unknown;
}
/**
 * The column this one qualifies, and how: its uncertainty, detection limit or flag.
 */
export interface AncillaryOf {
  field: Field1;
  role: Role;
  [k: string]: unknown;
}
export interface Example {
  [k: string]: unknown;
}
/**
 * A link from columns of this table to columns of another, such as a code list.
 */
export interface ForeignKey {
  fields: Fields2;
  reference: ForeignKeyReference;
  [k: string]: unknown;
}
/**
 * What a foreign key points at. With no `resource` it points into the same table.
 */
export interface ForeignKeyReference {
  fields: Fields3;
  resource?: Resource1;
  [k: string]: unknown;
}
/**
 * One file of a resource made of several files that only work together.
 */
export interface MemberFile {
  bytes?: Bytes;
  hash?: Hash;
  path: Path2;
  [k: string]: unknown;
}
export interface Data {
  [k: string]: unknown;
}
