/**
 * Reading a package folder the contributor chose or dropped, checking it against its
 * `checksums.sha256`, and uploading its files to their presigned links.
 */
import type { SubmittedFile, Upload } from "./api";

/** A file of the package, by its path from the package folder's root. */
export interface PackageFile {
  path: string;
  file: File;
}

/** A file to send: what the API is told about it, and the file itself. */
export type ReadyFile = SubmittedFile & { file: File };

export type Checked =
  | {
      ok: true;
      files: ReadyFile[];
      /** Files in the folder that `checksums.sha256` doesn't list, so aren't sent. */
      left: string[];
      manifest: { id: string; title: string | null };
    }
  | { ok: false; problem: string };

const MAX_PUT = 5 * 1024 ** 3;

/** Dot-files and dot-folders (`.DS_Store`, `.git/`) are the computer's, not the package's. */
const hidden = (path: string) => path.split("/").some((part) => part.startsWith("."));

/**
 * A directory input's files, each by its path from the chosen folder's root: the input names
 * them `<folder>/<path>`, and the folder's own name is dropped.
 */
export function fromFileList(list: FileList | File[]): PackageFile[] {
  return [...list]
    .map((file) => {
      const relative = file.webkitRelativePath || file.name;
      const slash = relative.indexOf("/");
      return { path: slash === -1 ? relative : relative.slice(slash + 1), file };
    })
    .filter(({ path }) => path && !hidden(path));
}

function readAll(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const entries: FileSystemEntry[] = [];
    const next = () =>
      reader.readEntries((batch) => {
        if (batch.length === 0) resolve(entries);
        else {
          entries.push(...batch);
          next();
        }
      }, reject);
    next();
  });
}

async function walk(entry: FileSystemEntry, prefix: string): Promise<PackageFile[]> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntry).file(resolve, reject),
    );
    return [{ path: prefix + entry.name, file }];
  }
  const children = await readAll((entry as FileSystemDirectoryEntry).createReader());
  const nested = await Promise.all(children.map((child) => walk(child, `${prefix}${entry.name}/`)));
  return nested.flat();
}

/**
 * Dropped entries: one dropped folder is the package, with paths from inside it; dropped files
 * (or several folders) keep their own names as paths.
 */
export async function fromEntries(entries: FileSystemEntry[]): Promise<PackageFile[]> {
  let files: PackageFile[];
  const only = entries[0];
  if (entries.length === 1 && only?.isDirectory) {
    const children = await readAll((only as FileSystemDirectoryEntry).createReader());
    files = (await Promise.all(children.map((child) => walk(child, "")))).flat();
  } else {
    files = (await Promise.all(entries.map((entry) => walk(entry, "")))).flat();
  }
  return files.filter(({ path }) => !hidden(path));
}

/** A drop's items as entries, read before the drop event ends (the list empties after). */
export function droppedEntries(items: DataTransferItemList): FileSystemEntry[] {
  return [...items]
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is FileSystemEntry => entry !== null);
}

/** `checksums.sha256` as `sha256sum` writes it: each line a hex digest, spaces, a path. */
function parseChecksums(text: string): Map<string, string> | null {
  const sums = new Map<string, string>();
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim()) continue;
    const match = /^([0-9a-fA-F]{64}) [ *](.+)$/.exec(line);
    if (!match) return null;
    sums.set(match[2]!.replace(/^\.\//, ""), match[1]!.toLowerCase());
  }
  return sums;
}

/** A file's SHA-256 in hex, with the browser's own hasher. */
export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * Check a package before anything is sent: it holds `datapackage.json` and `checksums.sha256`,
 * every file the checksums list is there and matches, and the manifest names its dataset.
 * The files sent are the listed ones and `checksums.sha256` itself. `onHashed` hears how many
 * files have been hashed, of how many.
 */
export async function checkPackage(
  files: PackageFile[],
  onHashed: (done: number, total: number) => void = () => {},
): Promise<Checked> {
  const byPath = new Map(files.map((entry) => [entry.path, entry.file]));
  const manifestFile = byPath.get("datapackage.json");
  const checksumsFile = byPath.get("checksums.sha256");
  if (!manifestFile) {
    return { ok: false, problem: "The folder has no datapackage.json at its top level." };
  }
  if (!checksumsFile) {
    return { ok: false, problem: "The folder has no checksums.sha256 at its top level." };
  }
  const sums = parseChecksums(await checksumsFile.text());
  if (!sums) {
    return { ok: false, problem: "checksums.sha256 isn't in the form sha256sum writes." };
  }
  let manifest: { id?: unknown; title?: unknown };
  try {
    manifest = JSON.parse(await manifestFile.text()) as { id?: unknown; title?: unknown };
  } catch {
    return { ok: false, problem: "datapackage.json isn't valid JSON." };
  }
  if (typeof manifest.id !== "string" || !/^[A-Za-z0-9_-]{1,200}$/.test(manifest.id)) {
    return { ok: false, problem: "datapackage.json has no id the archive can use." };
  }
  for (const path of sums.keys()) {
    if (!byPath.has(path)) {
      return {
        ok: false,
        problem: `${path} is listed in checksums.sha256 but isn't in the folder.`,
      };
    }
  }
  const ready: ReadyFile[] = [];
  const listed = [...sums.keys(), "checksums.sha256"];
  let done = 0;
  onHashed(done, listed.length);
  for (const path of listed) {
    const file = byPath.get(path)!;
    if (file.size > MAX_PUT) {
      return { ok: false, problem: `${path} is over 5 GB, more than the archive takes.` };
    }
    // One file at a time, so only one is held in memory.
    const sha256 = await sha256Hex(file);
    const expected = sums.get(path);
    if (expected !== undefined && expected !== sha256) {
      return { ok: false, problem: `${path} doesn't match its checksum in checksums.sha256.` };
    }
    ready.push({ path, size: file.size, sha256, file });
    onHashed((done += 1), listed.length);
  }
  const left = files
    .map((entry) => entry.path)
    .filter((path) => !listed.includes(path))
    .toSorted();
  const title = typeof manifest.title === "string" ? manifest.title : null;
  return { ok: true, files: ready, left, manifest: { id: manifest.id, title } };
}

/**
 * PUT a file to its presigned link with the headers the link was signed with (the checksum),
 * through XMLHttpRequest so its progress can be shown. `onProgress` hears the bytes sent.
 */
export function uploadFile(
  upload: Upload,
  file: Blob,
  onProgress: (loaded: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", upload.url);
    for (const [name, value] of Object.entries(upload.headers)) {
      request.setRequestHeader(name, value);
    }
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded);
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress(file.size);
        resolve();
      } else reject(new Error(`the upload of ${upload.path} was refused (${request.status})`));
    };
    request.onerror = () => reject(new Error(`the upload of ${upload.path} didn't reach storage`));
    request.send(file);
  });
}
