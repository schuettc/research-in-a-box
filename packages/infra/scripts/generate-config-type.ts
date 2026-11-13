// Write the construct's ArchiveConfig type from the contract's committed JSON Schema.
//
// Formatted with the repo's Prettier config, wherever <out> is, so the drift check can diff it.
//
// Usage: npx tsx packages/infra/scripts/generate-config-type.ts <schema> <out>

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { compile, type JSONSchema } from "json-schema-to-typescript";
import { format, resolveConfig } from "prettier";

const BANNER =
  "// Generated from the archive contract's JSON Schema by\n" +
  "// packages/infra/scripts/generate-config-type.ts (`just schema`). Do not edit.";

const [schemaPath, outPath] = process.argv.slice(2);
if (!schemaPath || !outPath) {
  throw new Error("usage: generate-config-type.ts <schema> <out>");
}

const schema = JSON.parse(readFileSync(schemaPath, "utf-8")) as {
  $defs: Record<string, JSONSchema>;
};
const archiveConfig = schema.$defs["ArchiveConfig"];
if (!archiveConfig) {
  throw new Error(`${schemaPath} has no ArchiveConfig definition`);
}

const code = await compile(
  { ...archiveConfig, $defs: schema.$defs } as JSONSchema,
  "ArchiveConfig",
  {
    bannerComment: BANNER,
    format: false,
    additionalProperties: false,
  },
);
const options = (await resolveConfig(fileURLToPath(import.meta.url))) ?? {};
writeFileSync(outPath, await format(code, { ...options, parser: "typescript" }), "utf-8");
