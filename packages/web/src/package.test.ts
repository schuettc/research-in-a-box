import { statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, expect, test, vi } from "vitest";
import { checkPackage, fromEntries, fromFileList, uploadFile, type PackageFile } from "./package";
import { FakeXhr, SAMPLE, sampleFiles } from "./test-fixtures";

afterEach(() => vi.unstubAllGlobals());

test("paths are relative to the package folder's root, and hidden files are skipped", () => {
  const extra = new File(["x"], ".DS_Store");
  Object.defineProperty(extra, "webkitRelativePath", { value: "sample-package/.DS_Store" });

  const files = fromFileList([...sampleFiles(), extra]);

  const paths = files.map((file) => file.path);
  expect(paths).toContain("datapackage.json");
  expect(paths).toContain("data/codes/condition-codes.csv");
  expect(paths).not.toContain(".DS_Store");
  expect(paths.every((path) => !path.startsWith("sample-package/"))).toBe(true);
});

test("the sample package checks: every listed file matches, and its id and title are read", async () => {
  const checked = await checkPackage(fromFileList(sampleFiles()));

  if (!checked.ok) throw new Error(checked.problem);
  expect(checked.manifest).toEqual({
    id: "stream-temperature-sample",
    title: "Stream temperature at three invented sites",
  });
  const paths = checked.files.map((file) => file.path);
  expect(paths).toContain("checksums.sha256");
  expect(paths).toContain("data/logger.csv");
  // _build/ isn't listed in checksums.sha256, so it isn't part of the package.
  expect(checked.left).toEqual(["_build/GAPS.md", "_build/make.py"]);
  const logger = checked.files.find((file) => file.path === "data/logger.csv");
  expect(logger?.sha256).toBe("1b8a6b3736dfbb165673581395b27d1a4e29ec3d90de3acb9a3cc98a72eeb341");
  expect(logger?.size).toBe(statSync(join(SAMPLE, "data/logger.csv")).size);
});

test("a folder without checksums.sha256 is refused", async () => {
  const checked = await checkPackage(fromFileList(sampleFiles({}, ["checksums.sha256"])));

  expect(checked.ok).toBe(false);
  if (!checked.ok) expect(checked.problem).toMatch(/no checksums\.sha256/);
});

test("a folder without datapackage.json is refused", async () => {
  const checked = await checkPackage(fromFileList(sampleFiles({}, ["datapackage.json"])));

  expect(checked.ok).toBe(false);
  if (!checked.ok) expect(checked.problem).toMatch(/no datapackage\.json/);
});

test("a changed file is named as not matching its checksum", async () => {
  const checked = await checkPackage(
    fromFileList(sampleFiles({ "data/logger.csv": "site,temp\nS1,99\n" })),
  );

  expect(checked.ok).toBe(false);
  if (!checked.ok) {
    expect(checked.problem).toBe("data/logger.csv doesn't match its checksum in checksums.sha256.");
  }
});

test("a file listed in checksums.sha256 but missing from the folder is named", async () => {
  const checked = await checkPackage(fromFileList(sampleFiles({}, ["docs/methods.md"])));

  expect(checked.ok).toBe(false);
  if (!checked.ok) expect(checked.problem).toMatch(/docs\/methods\.md is listed/);
});

test("a dropped folder is read through its entries, with paths from the folder's root", async () => {
  const file = (name: string, text: string) => ({
    isFile: true,
    isDirectory: false,
    name,
    file: (done: (file: File) => void) => done(new File([text], name)),
  });
  const dir = (name: string, children: object[]) => ({
    isFile: false,
    isDirectory: true,
    name,
    createReader: () => {
      let given = false;
      return {
        readEntries: (done: (entries: object[]) => void) => {
          const batch = given ? [] : children;
          given = true;
          done(batch);
        },
      };
    },
  });
  const root = dir("pkg", [file("datapackage.json", "{}"), dir("data", [file("a.csv", "x")])]);

  const files: PackageFile[] = await fromEntries([root as unknown as FileSystemEntry]);

  expect(files.map((f) => f.path).toSorted()).toEqual(["data/a.csv", "datapackage.json"]);
});

test("an upload PUTs the file to its link with the checksum header, reporting progress", async () => {
  FakeXhr.sent = [];
  FakeXhr.status = 200;
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  const seen: number[] = [];
  const file = new File(["hello"], "a.csv");

  await uploadFile(
    {
      path: "a.csv",
      url: "https://staging.example/a.csv?sig",
      headers: { "x-amz-checksum-sha256": "c2lnbg==" },
    },
    file,
    (loaded) => seen.push(loaded),
  );

  expect(FakeXhr.sent).toEqual([
    {
      method: "PUT",
      url: "https://staging.example/a.csv?sig",
      headers: { "x-amz-checksum-sha256": "c2lnbg==" },
      body: file,
    },
  ]);
  expect(seen.at(-1)).toBe(5);
});

test("an upload S3 refuses is an error", async () => {
  FakeXhr.status = 403;
  vi.stubGlobal("XMLHttpRequest", FakeXhr);

  await expect(
    uploadFile(
      { path: "a", url: "https://x", headers: { "x-amz-checksum-sha256": "c" } },
      new File(["a"], "a"),
      () => {},
    ),
  ).rejects.toThrow(/403/);
});
