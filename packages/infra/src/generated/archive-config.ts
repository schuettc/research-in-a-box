// Generated from the archive contract's JSON Schema by
// packages/infra/scripts/generate-config-type.ts (`just schema`). Do not edit.

export type Access = ("open" | "restricted" | "by-request" | "description-only")[];
export type Alertemail = string;
export type Retentiondays = number;
export type Waf = boolean;
export type Monthlybudgetusd = number;
/**
 * @minItems 1
 */
export type Stages = [Stage, ...Stage[]];
export type Account = string | null;
export type Name = string;
export type Region = string | null;
export type Licenses = string[];
export type Profiles = string[];
export type Publisher = string;
export type Required = string[];
export type Themes = string[];
export type Field = string;
export type Name1 = string;
export type Terms = string[];
export type Url = string | null;
export type Vocabularies = Vocabulary[];

/**
 * Which profiles apply, extra required fields, vocabularies, themes, the licenses and
 * access levels offered, and the publisher the archive fills in at publish.
 */
export interface ArchiveConfig {
  access?: Access;
  infrastructure?: Infrastructure | null;
  licenses?: Licenses;
  profiles?: Profiles;
  publisher: Publisher;
  required?: Required;
  themes?: Themes;
  vocabularies?: Vocabularies;
  [k: string]: unknown;
}
/**
 * Where and how the archive is deployed.
 */
export interface Infrastructure {
  alertEmail: Alertemail;
  modules?: Modules;
  monthlyBudgetUsd?: Monthlybudgetusd;
  stages?: Stages;
}
/**
 * The optional parts, each built only when switched on.
 */
export interface Modules {
  objectLock?: ObjectLock | null;
  waf?: Waf;
}
/**
 * Write-once locking of the archive bucket, in governance mode.
 */
export interface ObjectLock {
  retentionDays: Retentiondays;
}
/**
 * One deployment of the archive, its own stack, optionally in its own account and region.
 */
export interface Stage {
  account?: Account;
  name: Name;
  region?: Region;
}
/**
 * A vocabulary for a manifest field, named by URL or given as terms.
 */
export interface Vocabulary {
  field: Field;
  name: Name1;
  terms?: Terms;
  url?: Url;
  [k: string]: unknown;
}
