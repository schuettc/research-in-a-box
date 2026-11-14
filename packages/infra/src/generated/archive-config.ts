// Generated from the archive contract's JSON Schema by
// packages/infra/scripts/generate-config-type.ts (`just schema`). Do not edit.

export type Access = ("open" | "restricted" | "by-request" | "description-only")[];
export type Contact = string | null;
export type Favicon = string | null;
export type Font = string | null;
export type Intro = string | null;
export type Logo = string | null;
export type Name = string | null;
export type Primarycolor = string | null;
export type Alertemail = string;
export type Model = "amazon.titan-embed-text-v2:0";
export type Retentiondays = number;
export type Waf = boolean;
export type Monthlybudgetusd = number;
/**
 * @minItems 1
 */
export type Stages = [Stage, ...Stage[]];
export type Account = string | null;
export type Name1 = string;
export type Region = string | null;
export type Licenses = string[];
export type Profiles = string[];
export type Publisher = string;
export type Required = string[];
export type Themes = string[];
export type Field = string;
export type Name2 = string;
export type Terms = string[];
export type Url = string | null;
export type Vocabularies = Vocabulary[];

/**
 * Which profiles apply, extra required fields, vocabularies, themes, the licenses and
 * access levels offered, and the publisher the archive fills in at publish.
 */
export interface ArchiveConfig {
  access?: Access;
  brand?: Brand | null;
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
 * How the archive presents itself: the app, the sign-in page and the invitation email.
 *
 * `logo` and `favicon` are paths relative to the config file; they are checked only when
 * the config is loaded from its file, since a deployed copy travels without them.
 */
export interface Brand {
  contact?: Contact;
  favicon?: Favicon;
  font?: Font;
  intro?: Intro;
  logo?: Logo;
  name?: Name;
  primaryColor?: Primarycolor;
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
  embeddings?: Embeddings | null;
  objectLock?: ObjectLock | null;
  waf?: Waf;
}
/**
 * Semantic search: an embedding on each dataset item and a vector index to search them.
 */
export interface Embeddings {
  model?: Model;
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
  name: Name1;
  region?: Region;
}
/**
 * A vocabulary for a manifest field, named by URL or given as terms.
 */
export interface Vocabulary {
  field: Field;
  name: Name2;
  terms?: Terms;
  url?: Url;
  [k: string]: unknown;
}
