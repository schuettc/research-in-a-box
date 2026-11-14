import { Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import type { CfnTable, Table } from "aws-cdk-lib/aws-dynamodb";
import { expect, test } from "vitest";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

function archive(stage = "prod"): { archive: ResearchArchive; template: Template } {
  const stack = new Stack(testApp(), "S");
  const built = new ResearchArchive(stack, "Archive", {
    config: {
      publisher: "P",
      infrastructure: { alertEmail: "a@example.org", stages: [{ name: "prod" }, { name: "dev" }] },
    },
    stage,
  });
  return { archive: built, template: Template.fromStack(stack) };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Resource = { Properties: Record<string, any>; DeletionPolicy?: string };

function tableOf(template: Template, table: Table): Resource {
  const id = Stack.of(table).getLogicalId(table.node.defaultChild as CfnTable);
  return template.toJSON().Resources[id] as Resource;
}

function stringKeys(...names: string[]) {
  return names.map((name) => ({ AttributeName: name, AttributeType: "S" }));
}

test("there are two catalog tables with PK, SK and GSI1, on demand, without point-in-time recovery", () => {
  const { archive: a, template } = archive();

  for (const table of [a.catalogTables.a, a.catalogTables.b]) {
    const props = tableOf(template, table).Properties;
    expect(props.BillingMode).toBe("PAY_PER_REQUEST");
    expect(props.KeySchema).toEqual([
      { AttributeName: "PK", KeyType: "HASH" },
      { AttributeName: "SK", KeyType: "RANGE" },
    ]);
    expect(props.AttributeDefinitions).toEqual(
      expect.arrayContaining(stringKeys("PK", "SK", "GSI1PK", "GSI1SK")),
    );
    expect(props.GlobalSecondaryIndexes).toEqual([
      {
        IndexName: "GSI1",
        KeySchema: [
          { AttributeName: "GSI1PK", KeyType: "HASH" },
          { AttributeName: "GSI1SK", KeyType: "RANGE" },
        ],
        Projection: { ProjectionType: "ALL" },
      },
    ]);
    expect(props.PointInTimeRecoverySpecification).toBeUndefined();
    expect(props.TableName).toBeUndefined();
  }
  // Plan 4's seven, plus the read API's UsageResponses.
  expect(Object.keys(template.findResources("AWS::DynamoDB::Table"))).toHaveLength(8);
});

test("no table is a global table", () => {
  expect(archive().template.findResources("AWS::DynamoDB::GlobalTable")).toEqual({});
});

test("the active-catalog parameter is named for the stage and starts at A", () => {
  archive("dev").template.hasResourceProperties("AWS::SSM::Parameter", {
    Name: "/research-archive/dev/catalog-active",
    Type: "String",
    Value: "A",
  });
});

test("each operational table has its key and point-in-time recovery", () => {
  const { archive: a, template } = archive();
  const keys = (hash: string, range?: string) => [
    { AttributeName: hash, KeyType: "HASH" },
    ...(range ? [{ AttributeName: range, KeyType: "RANGE" }] : []),
  ];
  const expected: [Table, ReturnType<typeof keys>][] = [
    [a.submissions, keys("submissionId")],
    [a.reviews, keys("submissionId", "eventKey")],
    [a.settings, keys("name")],
    [a.userProfiles, keys("userId")],
    [a.downloadCounts, keys("datasetId", "month")],
  ];

  for (const [table, keySchema] of expected) {
    const props = tableOf(template, table).Properties;
    expect(props.KeySchema).toEqual(keySchema);
    expect(props.BillingMode).toBe("PAY_PER_REQUEST");
    expect(props.PointInTimeRecoverySpecification).toEqual({ PointInTimeRecoveryEnabled: true });
  }

  const submissions = tableOf(template, a.submissions).Properties;
  expect(submissions.GlobalSecondaryIndexes).toEqual([
    {
      IndexName: "byStatus",
      KeySchema: keys("status", "createdAt"),
      Projection: { ProjectionType: "ALL" },
    },
    {
      IndexName: "bySubmitter",
      KeySchema: keys("submitter", "createdAt"),
      Projection: { ProjectionType: "ALL" },
    },
  ]);
  expect(submissions.AttributeDefinitions).toEqual(
    expect.arrayContaining(stringKeys("submissionId", "status", "createdAt", "submitter")),
  );
});

test("prod tables have deletion protection and are retained; a dev stage's are not", () => {
  const prod = Object.values(archive("prod").template.findResources("AWS::DynamoDB::Table"));
  const dev = Object.values(archive("dev").template.findResources("AWS::DynamoDB::Table"));

  expect(prod).toHaveLength(8);
  for (const table of prod) {
    expect(table.DeletionPolicy).toBe("Retain");
    expect(table.Properties.DeletionProtectionEnabled).toBe(true);
  }
  expect(dev).toHaveLength(8);
  for (const table of dev) {
    expect(table.DeletionPolicy).toBe("Delete");
    expect(table.Properties.DeletionProtectionEnabled).not.toBe(true);
  }
});

test("with the embeddings module each catalog table has the datasets vector index, and none without", () => {
  const stack = new Stack(testApp(), "E");
  const built = new ResearchArchive(stack, "Archive", {
    config: {
      publisher: "P",
      infrastructure: {
        alertEmail: "a@example.org",
        stages: [{ name: "prod" }],
        modules: { embeddings: {} },
      },
    },
    stage: "prod",
  });
  const template = Template.fromStack(stack);

  for (const table of [built.catalogTables.a, built.catalogTables.b]) {
    expect(tableOf(template, table).Properties.VectorIndexes).toEqual([
      {
        IndexName: "datasets",
        VectorAttribute: { AttributeName: "embedding" },
        Dimensions: 1024,
        DistanceFunction: "COSINE",
        Projection: { ProjectionType: "KEYS_ONLY" },
      },
    ]);
  }
  expect(JSON.stringify(archive().template.toJSON())).not.toContain("VectorIndexes");
});
