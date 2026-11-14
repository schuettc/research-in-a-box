import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { App, Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import type { CfnParameter } from "aws-cdk-lib/aws-ssm";
import { expect, test } from "vitest";
import { createApp, stackName } from "../bin/app";
import type { ArchiveConfig } from "../src/generated/archive-config";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

function configFile(yaml: string): string {
  const path = join(mkdtempSync(join(tmpdir(), "archive-config-")), "archive.yaml");
  writeFileSync(path, yaml, "utf-8");
  return path;
}

const INFRASTRUCTURE = "infrastructure:\n  alertEmail: a@example.org\n";

test("the default app makes ResearchArchive-prod from the committed archive.yaml, with the Repo tag", () => {
  const assembly = createApp().synth();
  const stack = assembly.getStackByName(stackName("prod"));

  expect(stack.stackName).toBe("ResearchArchive-prod");
  expect(stack.tags).toEqual({ Repo: "schuettc/research-in-a-box" });
});

test("a second stage makes a second stack", () => {
  const app = createApp(
    configFile(`publisher: P\n${INFRASTRUCTURE}  stages:\n    - name: prod\n    - name: dev\n`),
  );
  const assembly = app.synth();

  expect(assembly.stacks.map((s) => s.stackName).sort()).toEqual([
    "ResearchArchive-dev",
    "ResearchArchive-prod",
  ]);
  expect(assembly.getStackByName(stackName("dev")).tags).toEqual({
    Repo: "schuettc/research-in-a-box",
  });
});

test("a stage with an account and region sets the stack's environment", () => {
  const app = createApp(
    configFile(
      `publisher: P\n${INFRASTRUCTURE}  stages:\n` +
        "    - name: prod\n      account: '123456789012'\n      region: us-east-2\n" +
        "    - name: dev\n",
    ),
  );

  const prod = app.node.findChild(stackName("prod")) as Stack;
  const dev = app.node.findChild(stackName("dev")) as Stack;
  expect(prod.account).toBe("123456789012");
  expect(prod.region).toBe("us-east-2");
  expect(Stack.of(dev).environment).toBe("aws://unknown-account/unknown-region");
});

test("ARCHIVE_CONFIG points the default app at another config file", () => {
  const path = configFile(`publisher: P\n${INFRASTRUCTURE}  stages:\n    - name: test\n`);
  const previous = process.env.ARCHIVE_CONFIG;
  process.env.ARCHIVE_CONFIG = path;
  try {
    const assembly = createApp().synth();

    expect(assembly.stacks.map((s) => s.stackName)).toEqual(["ResearchArchive-test"]);
  } finally {
    if (previous === undefined) {
      delete process.env.ARCHIVE_CONFIG;
    } else {
      process.env.ARCHIVE_CONFIG = previous;
    }
  }
});

test("a config with no infrastructure section is refused with a clear message", () => {
  expect(() => createApp(configFile("publisher: P\n"))).toThrow(
    "archive.yaml needs an infrastructure section",
  );
});

test("a typo in modules is refused", () => {
  expect(() =>
    createApp(configFile(`publisher: P\n${INFRASTRUCTURE}  modules:\n    wafs: true\n`)),
  ).toThrow(/wafs/);
});

test("ResearchArchive refuses a stage not in the config", () => {
  const config: ArchiveConfig = {
    publisher: "P",
    infrastructure: { alertEmail: "a@example.org", stages: [{ name: "prod" }] },
  };
  const stack = new Stack(new App(), "S");

  expect(() => new ResearchArchive(stack, "Archive", { config, stage: "dev" })).toThrow(
    'stage "dev" is not in infrastructure.stages',
  );
});

test("the construct writes the config as JSON to the stage's standard archive-config parameter", () => {
  const config: ArchiveConfig = {
    publisher: "P",
    profiles: ["core"],
    infrastructure: { alertEmail: "a@example.org", stages: [{ name: "prod" }, { name: "dev" }] },
  };
  const stack = new Stack(testApp(), "S");
  const archive = new ResearchArchive(stack, "Archive", { config, stage: "dev" });
  const id = stack.getLogicalId(archive.archiveConfigParameter.node.defaultChild as CfnParameter);

  expect(Template.fromStack(stack).toJSON().Resources[id].Properties).toEqual({
    Name: "/research-archive/dev/archive-config",
    Type: "String",
    Tier: "Standard",
    Value: JSON.stringify(config),
  });
});

test("a config whose JSON is over 4096 bytes is refused at synth", () => {
  const config: ArchiveConfig = {
    publisher: "P".repeat(4096),
    infrastructure: { alertEmail: "a@example.org", stages: [{ name: "prod" }] },
  };
  const stack = new Stack(testApp(), "S");

  expect(() => new ResearchArchive(stack, "Archive", { config, stage: "prod" })).toThrow(
    /archive config is \d+ bytes as JSON; the SSM parameter holds at most 4096/,
  );
});
