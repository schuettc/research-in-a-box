import { readFileSync } from "node:fs";
import { Ajv2020 } from "ajv/dist/2020.js";
import { parse } from "yaml";
import type { ArchiveConfig, Stage } from "./generated/archive-config";

const SCHEMA_PATH = new URL("../../web/src/schema/archive-contract.schema.json", import.meta.url);

/** The stages a config deploys: those it names, or `prod` alone. */
export function stagesOf(config: ArchiveConfig): Stage[] {
  return config.infrastructure?.stages ?? [{ name: "prod" }];
}

/** Read an archive config file and validate it against the contract's committed schema. */
export function loadArchiveConfig(path: string): ArchiveConfig {
  const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf-8")) as {
    $defs: Record<string, object>;
  };
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  const validate = ajv.compile<ArchiveConfig>({
    ...schema.$defs["ArchiveConfig"],
    $defs: schema.$defs,
  });
  const config: unknown = parse(readFileSync(path, "utf-8"));
  if (!validate(config)) {
    const messages = (validate.errors ?? []).map((error) => {
      const extra =
        "additionalProperty" in error.params ? ` (${String(error.params.additionalProperty)})` : "";
      return `${error.instancePath || "/"} ${error.message ?? "is invalid"}${extra}`;
    });
    throw new Error(`${path} is not a valid archive config:\n${messages.join("\n")}`);
  }
  if (!config.infrastructure) {
    throw new Error("archive.yaml needs an infrastructure section");
  }
  return config;
}
