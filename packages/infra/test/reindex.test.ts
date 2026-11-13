import { Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import type { CfnTable } from "aws-cdk-lib/aws-dynamodb";
import type { CfnAlias } from "aws-cdk-lib/aws-lambda";
import { beforeAll, expect, test } from "vitest";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

let archive: ResearchArchive;
let stack: Stack;
let template: Template;

beforeAll(() => {
  stack = new Stack(testApp(), "S");
  archive = new ResearchArchive(stack, "Archive", {
    config: {
      publisher: "P",
      infrastructure: { alertEmail: "a@example.org", stages: [{ name: "prod" }] },
    },
    stage: "prod",
  });
  template = Template.fromStack(stack);
});

function reindexFunction(): { id: string; properties: Record<string, unknown> } {
  const fns = template.findResources("AWS::Lambda::Function", {
    Properties: { Handler: "archive_backend.reindex.handler" },
  });
  expect(Object.keys(fns)).toHaveLength(1);
  const [id, resource] = Object.entries(fns)[0] as [
    string,
    { Properties: Record<string, unknown> },
  ];
  return { id, properties: resource.Properties };
}

function tableArn(which: "a" | "b"): unknown {
  const table = archive.catalogTables[which].node.defaultChild as CfnTable;
  return { "Fn::GetAtt": [stack.getLogicalId(table), "Arn"] };
}

function statements(): { Action: string | string[]; Resource: unknown }[] {
  const { id } = reindexFunction();
  const role = (template.toJSON().Resources[id].Properties.Role as { "Fn::GetAtt": string[] })[
    "Fn::GetAtt"
  ][0];
  const policies = template.findResources("AWS::IAM::Policy", {
    Properties: { Roles: [{ Ref: role }] },
  });
  return Object.values(policies).flatMap(
    (p) =>
      (p as { Properties: { PolicyDocument: { Statement: never[] } } }).Properties.PolicyDocument
        .Statement,
  );
}

function actions(statement: { Action: string | string[] }): string[] {
  return Array.isArray(statement.Action) ? statement.Action : [statement.Action];
}

test("the reindex function is durable with a 12-hour execution timeout", () => {
  expect(reindexFunction().properties).toMatchObject({
    Runtime: "python3.13",
    Architectures: ["arm64"],
    Timeout: 900,
    MemorySize: 1024,
    DurableConfig: { ExecutionTimeout: 43200, RetentionPeriodInDays: 30 },
  });
});

test("it is invoked through a live alias, which the ReindexFunction output names", () => {
  const { id } = reindexFunction();
  const aliasId = stack.getLogicalId(archive.reindexFunction.node.defaultChild as CfnAlias);

  template.hasResourceProperties("AWS::Lambda::Alias", {
    Name: "live",
    FunctionName: { Ref: id },
  });
  template.hasOutput("ReindexFunction", { Value: { Ref: aliasId } });
});

test("it may start bulk operations and bulk-load both catalog tables", () => {
  const all = statements();

  expect(all).toContainEqual(
    expect.objectContaining({ Action: "dynamodb:StartBulkOperation", Resource: "*" }),
  );
  const bulk = all.find((s) => actions(s).includes("dynamodb:BulkPutItems"));
  expect(bulk).toBeDefined();
  expect(actions(bulk!).sort()).toEqual([
    "dynamodb:BulkPutItems",
    "dynamodb:DescribeBulkOperation",
  ]);
  const resources = bulk!.Resource as unknown[];
  for (const which of ["a", "b"] as const) {
    expect(resources).toContainEqual(tableArn(which));
    expect(resources).toContainEqual({
      "Fn::Join": ["", [tableArn(which), "/bulk-operation/*"]],
    });
  }
  for (const which of ["a", "b"] as const) {
    expect(
      all.some(
        (s) =>
          actions(s).includes("dynamodb:BatchWriteItem") &&
          JSON.stringify(s.Resource).includes(JSON.stringify(tableArn(which))),
      ),
    ).toBe(true);
  }
  expect(all.some((s) => actions(s).includes("ssm:PutParameter"))).toBe(true);
  expect(all.some((s) => actions(s).includes("sns:Publish"))).toBe(true);
  expect(
    all.some(
      (s) =>
        actions(s).includes("s3:PutObject") && JSON.stringify(s.Resource).includes("/reindex/*"),
    ),
  ).toBe(true);
});

test("its environment names both catalog tables, the active-catalog parameter, both buckets and the alert topic", () => {
  expect(reindexFunction().properties).toMatchObject({
    Environment: {
      Variables: {
        ARCHIVE_BUCKET: expect.anything(),
        DERIVED_BUCKET: expect.anything(),
        CATALOG_TABLE_A: {
          Ref: stack.getLogicalId(archive.catalogTables.a.node.defaultChild as CfnTable),
        },
        CATALOG_TABLE_B: {
          Ref: stack.getLogicalId(archive.catalogTables.b.node.defaultChild as CfnTable),
        },
        ACTIVE_CATALOG_PARAMETER: expect.anything(),
        ALERT_TOPIC_ARN: expect.anything(),
      },
    },
  });
});
