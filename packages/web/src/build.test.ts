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
  expect(html).toContain('<link rel="icon" href="/brand/favicon.svg"');
  const css = readdirSync(join(out, "assets"))
    .filter((name) => name.endsWith(".css"))
    .map((name) => readFileSync(join(out, "assets", name), "utf-8"))
    .join("");
  expect(css).toContain("#1e5631");
  expect(css).toContain("Charter");
  expect(readdirSync(join(out, "brand")).sort()).toEqual(["favicon.svg", "logo.svg"]);
  const js = readdirSync(join(out, "assets"))
    .filter((name) => name.endsWith(".js"))
    .map((name) => readFileSync(join(out, "assets", name), "utf-8"))
    .join("");
  expect(js).toContain("Northern Watershed Data Commons");
  expect(js).toContain("data@northern.example");
}, 60_000);
