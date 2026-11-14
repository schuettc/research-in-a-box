import { existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "vitest";

const ASSETS = fileURLToPath(new URL("../assets/python", import.meta.url));

// Lambda's limit on a function's unzipped code, layers included: 250 MB.
const LAMBDA_UNZIPPED_LIMIT = 250 * 1024 * 1024;

function sizeOf(path: string): number {
  return readdirSync(path, { withFileTypes: true }).reduce((total, entry) => {
    const child = join(path, entry.name);
    if (entry.isDirectory()) return total + sizeOf(child);
    return total + (entry.isFile() ? statSync(child).size : 0);
  }, 0);
}

test("the shared Lambda asset stays under Lambda's 250 MB unzipped limit", () => {
  expect(existsSync(ASSETS), "run just lambda-assets first").toBe(true);
  const bytes = sizeOf(ASSETS);
  console.log(`assets/python is ${(bytes / 1024 / 1024).toFixed(1)} MB unzipped`);

  expect(bytes).toBeLessThan(LAMBDA_UNZIPPED_LIMIT);
});

test("the shared Lambda asset carries archive-backend, the contract, cruise and DuckDB", () => {
  for (const pkg of ["archive_backend", "archive_contract", "cruise", "duckdb"]) {
    expect(existsSync(join(ASSETS, pkg)), pkg).toBe(true);
  }
});
