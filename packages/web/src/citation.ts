import type { Contributor, Manifest } from "./generated/manifest";

/** A contributor's display name: its title, else given and family name, else organization. */
export function personName(contributor: Contributor): string | null {
  if (contributor.title) return contributor.title;
  const parts = [contributor.givenName, contributor.familyName].filter(Boolean);
  if (parts.length) return parts.join(" ");
  return contributor.organization ?? null;
}

export function creatorNames(manifest: Manifest): string[] {
  return (manifest.contributors ?? [])
    .filter((c) => c.roles?.includes("creator"))
    .map(personName)
    .filter((name): name is string => Boolean(name));
}

const squash = (text: string) => text.split(/\s+/).filter(Boolean).join(" ");

/**
 * The citation as the generated README builds it (`archive:citation`, else creators, year,
 * title, version and id), then the versioned URL the reader cites.
 */
export function citation(manifest: Manifest, url: string): string | null {
  if (manifest["archive:citation"]) return `${squash(manifest["archive:citation"])} ${url}`;
  if (!manifest.title) return null;
  const parts: string[] = [];
  const names = creatorNames(manifest);
  if (names.length) {
    const year = manifest.created ? ` (${manifest.created.slice(0, 4)})` : "";
    parts.push(`${names.join(", ")}${year}.`);
  }
  parts.push(`${manifest.title.replace(/\.+$/, "")}.`);
  if (manifest.version) parts.push(`Version ${manifest.version}.`);
  if (manifest.id) parts.push(`${manifest.id}.`);
  parts.push(url);
  return parts.join(" ");
}
