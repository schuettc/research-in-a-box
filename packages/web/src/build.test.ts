// @vitest-environment node
import { mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";
import { afterEach, expect, test } from "vitest";

const CONFIG_FILE = fileURLToPath(new URL("../vite.config.ts", import.meta.url));
const before = process.env.ARCHIVE_CONFIG;

afterEach(() => {
  if (before === undefined) delete process.env.ARCHIVE_CONFIG;
  else process.env.ARCHIVE_CONFIG = before;
});

test("a build with a second brand takes its colour, name, logo and favicon", async () => {
  const dir = mkdtempSync(join(tmpdir(), "brand-"));
  writeFileSync(join(dir, "mark.svg"), '<svg xmlns="http://www.w3.org/2000/svg"/>');
  writeFileSync(join(dir, "icon.svg"), '<svg xmlns="http://www.w3.org/2000/svg"/>');
  writeFileSync(
    join(dir, "archive.yaml"),
    "publisher: Northern Watershed Group\n" +
      "brand:\n" +
      "  name: Northern Watershed Data Commons\n" +
      "  contact: data@northern.example\n" +
      "  logo: mark.svg\n" +
      "  favicon: icon.svg\n" +
      "  primaryColor: '#1e5631'\n" +
      "  font: Charter, Georgia, serif\n",
  );
  process.env.ARCHIVE_CONFIG = join(dir, "archive.yaml");
  const out = join(dir, "dist");

  await build({ configFile: CONFIG_FILE, logLevel: "silent", build: { outDir: out } });

  const html = readFileSync(join(out, "index.html"), "utf-8");
  expect(html).toContain("<title>Northern Watershed Data Commons</title>");
  expect(html).toMatch(/<link rel="icon" href="\/brand\/favicon-[0-9a-f]{8}\.svg"/);
  const css = readdirSync(join(out, "assets"))
    .filter((name) => name.endsWith(".css"))
    .map((name) => readFileSync(join(out, "assets", name), "utf-8"))
    .join("");
  expect(css).toContain("#1e5631");
  expect(css).toContain("Charter");
  // The app's copies are named by their content; logo.svg is the static pages' stable copy.
  expect(readdirSync(join(out, "brand")).sort()).toEqual([
    expect.stringMatching(/^favicon-[0-9a-f]{8}\.svg$/),
    expect.stringMatching(/^logo-[0-9a-f]{8}\.svg$/),
    "logo.svg",
  ]);
  const js = readdirSync(join(out, "assets"))
    .filter((name) => name.endsWith(".js"))
    .map((name) => readFileSync(join(out, "assets", name), "utf-8"))
    .join("");
  expect(js).toContain("Northern Watershed Data Commons");
  expect(js).toContain("data@northern.example");
}, 60_000);

/** Build with a brand whose logo is `logo`, and return the logo URL index.html's app is given. */
async function logoUrl(logo: string): Promise<string> {
  const dir = mkdtempSync(join(tmpdir(), "brand-"));
  writeFileSync(join(dir, "mark.svg"), logo);
  writeFileSync(join(dir, "archive.yaml"), "publisher: P\nbrand:\n  logo: mark.svg\n");
  process.env.ARCHIVE_CONFIG = join(dir, "archive.yaml");
  const out = join(dir, "dist");
  await build({ configFile: CONFIG_FILE, logLevel: "silent", build: { outDir: out } });
  const js = readdirSync(join(out, "assets"))
    .filter((name) => name.endsWith(".js"))
    .map((name) => readFileSync(join(out, "assets", name), "utf-8"))
    .join("");
  const url = /\/brand\/logo-[0-9a-f]{8}\.svg/.exec(js)?.[0];
  expect(url).toBeDefined();
  expect(readdirSync(join(out, "brand"))).toContain(url!.slice("/brand/".length));
  return url!;
}

test("a rebrand's logo gets a new URL, so a year-long cache never serves the old one", async () => {
  const first = await logoUrl('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>');
  const second = await logoUrl('<svg xmlns="http://www.w3.org/2000/svg"><circle/></svg>');

  expect(second).not.toBe(first);
}, 60_000);
