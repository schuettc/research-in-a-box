import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";
import type { Manifest } from "./generated/manifest";
import { citation } from "./citation";

const SAMPLE = join(import.meta.dirname, "../../../examples/sample-package");
const URL_ = "https://archive.example.org/datasets/stream-temperature-sample/v1";

test("the sample's citation is the README's, ending with the versioned URL", () => {
  const manifest = JSON.parse(readFileSync(join(SAMPLE, "datapackage.json"), "utf-8")) as Manifest;
  const readme = readFileSync(join(SAMPLE, "README.md"), "utf-8").split("\n");
  const cited = readme[readme.indexOf("## Citation") + 2];

  expect(citation(manifest, URL_)).toBe(`${cited} ${URL_}`);
});

test("with no archive:citation, it is built from the creators, year, title, version and id", () => {
  const manifest: Manifest = {
    id: "ds-1",
    title: "Lake levels.",
    version: "3",
    created: "2021-04-02T00:00:00Z",
    contributors: [
      { title: "Ada Invented", roles: ["creator"] },
      { givenName: "Ben", familyName: "Placeholder", roles: ["creator"] },
      { title: "Cy Curator", roles: ["data-curator"] },
    ],
  };

  expect(citation(manifest, URL_)).toBe(
    `Ada Invented, Ben Placeholder (2021). Lake levels. Version 3. ds-1. ${URL_}`,
  );
});

test("a manifest with no title has no citation", () => {
  expect(citation({ id: "ds-1" }, URL_)).toBeNull();
});
