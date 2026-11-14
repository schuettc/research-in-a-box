import { Stack } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import type { CfnAlias } from "aws-cdk-lib/aws-lambda";
import type { CfnBucket } from "aws-cdk-lib/aws-s3";
import { beforeAll, expect, test } from "vitest";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

let archive: ResearchArchive;
let stack: Stack;
let template: Template;

type Statement = { Action: string | string[]; Resource: unknown; Condition?: unknown };

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

function fn(handler: string): { id: string; properties: Record<string, unknown> } {
  const fns = template.findResources("AWS::Lambda::Function", {
    Properties: { Handler: handler },
  });
  expect(Object.keys(fns)).toHaveLength(1);
  const [id, resource] = Object.entries(fns)[0] as [
    string,
    { Properties: Record<string, unknown> },
  ];
  return { id, properties: resource.Properties };
}

const INGEST = "archive_backend.ingest.handler";
const SUBMISSIONS = "archive_backend.submissions.handler";

function statementsOfRole(role: string): Statement[] {
  const policies = template.findResources("AWS::IAM::Policy", {
    Properties: { Roles: [{ Ref: role }] },
  });
  return Object.values(policies).flatMap(
    (p) =>
      (p as { Properties: { PolicyDocument: { Statement: Statement[] } } }).Properties
        .PolicyDocument.Statement,
  );
}

function statements(handler: string): Statement[] {
  const { properties } = fn(handler);
  return statementsOfRole((properties.Role as { "Fn::GetAtt": string[] })["Fn::GetAtt"][0]!);
}

function actions(statement: { Action: string | string[] }): string[] {
  return Array.isArray(statement.Action) ? statement.Action : [statement.Action];
}

function logicalId(construct: { node: { defaultChild?: unknown } }): string {
  return stack.getLogicalId(construct.node.defaultChild as CfnBucket);
}

test("the ingest function is durable for a year, with 15 minutes, 2048 MB and 10 GiB of /tmp", () => {
  expect(fn(INGEST).properties).toMatchObject({
    Runtime: "python3.13",
    Architectures: ["arm64"],
    Timeout: 900,
    MemorySize: 2048,
    EphemeralStorage: { Size: 10240 },
    DurableConfig: { ExecutionTimeout: 365 * 24 * 3600, RetentionPeriodInDays: 30 },
  });
});

test("it is invoked through a live alias, which the IngestFunction output names", () => {
  const aliasId = stack.getLogicalId(archive.ingestFunction.node.defaultChild as CfnAlias);

  template.hasResourceProperties("AWS::Lambda::Alias", {
    Name: "live",
    FunctionName: { Ref: fn(INGEST).id },
  });
  template.hasOutput("IngestFunction", { Value: { Ref: aliasId } });
});

test("every environment variable either handler reads is set", () => {
  const ingest = fn(INGEST).properties.Environment as { Variables: Record<string, unknown> };
  const api = fn(SUBMISSIONS).properties.Environment as { Variables: Record<string, unknown> };

  expect(Object.keys(ingest.Variables).sort()).toEqual(
    [
      "SUBMISSIONS_TABLE",
      "REVIEWS_TABLE",
      "SETTINGS_TABLE",
      "STAGING_BUCKET",
      "CURATOR_TOPIC_ARN",
      "ALERT_TOPIC_ARN",
      "ARCHIVE_CONFIG_PARAMETER",
      "ARCHIVE_BUCKET",
      "DERIVED_BUCKET",
      "ACTIVE_CATALOG_PARAMETER",
      "CATALOG_TABLE_A",
      "CATALOG_TABLE_B",
      "SITE_DOMAIN",
    ].sort(),
  );
  expect(ingest.Variables.CURATOR_TOPIC_ARN).toEqual({ Ref: logicalId(archive.curatorTopic) });
  expect(ingest.Variables.SITE_DOMAIN).toEqual({
    "Fn::GetAtt": [logicalId(archive.distribution), "DomainName"],
  });
  expect(Object.keys(api.Variables).sort()).toEqual(
    [
      "SUBMISSIONS_TABLE",
      "REVIEWS_TABLE",
      "SETTINGS_TABLE",
      "STAGING_BUCKET",
      "INGEST_ALIAS_ARN",
      "ACTIVE_CATALOG_PARAMETER",
      "CATALOG_TABLE_A",
      "CATALOG_TABLE_B",
    ].sort(),
  );
  expect(JSON.stringify(api.Variables.INGEST_ALIAS_ARN)).toContain(
    ":function:ResearchArchive-prod-Ingest:live",
  );
});

test("each submissions route has its method behind the Cognito authorizer", () => {
  const [authorizer] = Object.keys(template.findResources("AWS::ApiGateway::Authorizer"));
  // Other plans hang their own {id} resources off /api, so each part is found under its parent.
  const resource = (pathPart: string, parent?: string): string => {
    const ids = Object.entries(
      template.findResources("AWS::ApiGateway::Resource", { Properties: { PathPart: pathPart } }),
    )
      .filter(
        ([, r]) =>
          parent === undefined ||
          JSON.stringify((r as { Properties: { ParentId: unknown } }).Properties.ParentId) ===
            JSON.stringify({ Ref: parent }),
      )
      .map(([id]) => id);
    expect(ids).toHaveLength(1);
    return ids[0]!;
  };
  const submissions = resource("submissions");
  const policy = resource("policy", submissions);
  const id = resource("{id}", submissions);
  const routes: [string, string][] = [
    ["POST", submissions],
    ["GET", submissions],
    ["GET", policy],
    ["PUT", policy],
    ["GET", id],
    ["POST", resource("uploads", id)],
    ["POST", resource("submit", id)],
    ["POST", resource("decision", id)],
  ];

  for (const [method, resourceId] of routes) {
    template.hasResourceProperties("AWS::ApiGateway::Method", {
      HttpMethod: method,
      ResourceId: { Ref: resourceId },
      AuthorizationType: "COGNITO_USER_POOLS",
      AuthorizerId: { Ref: authorizer },
      Integration: {
        Uri: {
          "Fn::Join": ["", Match.arrayWith([{ "Fn::GetAtt": [fn(SUBMISSIONS).id, "Arn"] }])],
        },
      },
    });
  }
});

test("GuardDuty scans and tags the staging bucket's incoming/ prefix, with the documented role", () => {
  const staging = logicalId(archive.stagingBucket);
  const plans = template.findResources("AWS::GuardDuty::MalwareProtectionPlan");
  expect(Object.keys(plans)).toHaveLength(1);
  const plan = Object.values(plans)[0]!.Properties as {
    ProtectedResource: unknown;
    Actions: unknown;
    Role: { "Fn::GetAtt": [string, string] };
  };

  expect(plan.ProtectedResource).toEqual({
    S3Bucket: { BucketName: { Ref: staging }, ObjectPrefixes: ["incoming/"] },
  });
  expect(plan.Actions).toEqual({ Tagging: { Status: "ENABLED" } });
  const role = plan.Role["Fn::GetAtt"][0];
  expect(plan.Role["Fn::GetAtt"][1]).toBe("Arn");
  const roleProperties = template.toJSON().Resources[role].Properties as {
    AssumeRolePolicyDocument: { Statement: unknown[] };
    Policies: { PolicyDocument: { Statement: Statement[] } }[];
  };
  expect(roleProperties.AssumeRolePolicyDocument.Statement).toEqual([
    expect.objectContaining({
      Action: "sts:AssumeRole",
      Principal: { Service: "malware-protection-plan.guardduty.amazonaws.com" },
    }),
  ]);

  const all = roleProperties.Policies.flatMap((p) => p.PolicyDocument.Statement);
  const scan = all.find((s) => actions(s).includes("s3:GetObject"));
  expect(actions(scan!).sort()).toEqual(["s3:GetObject", "s3:GetObjectVersion"]);
  expect(JSON.stringify(scan!.Resource)).toContain("/incoming/*");
  const tag = all.find((s) => actions(s).includes("s3:PutObjectTagging"));
  expect(actions(tag!).sort()).toEqual([
    "s3:GetObjectTagging",
    "s3:GetObjectVersionTagging",
    "s3:PutObjectTagging",
    "s3:PutObjectVersionTagging",
  ]);
  expect(JSON.stringify(tag!.Resource)).toContain("/incoming/*");
  const validation = all.find((s) => actions(s).includes("s3:PutObject"));
  expect(JSON.stringify(validation!.Resource)).toContain(
    "/malware-protection-resource-validation-object",
  );
  const rule = all.find((s) => actions(s).includes("events:PutRule"));
  expect(rule!.Condition).toEqual({
    StringLike: { "events:ManagedBy": "malware-protection-plan.guardduty.amazonaws.com" },
  });
  expect(JSON.stringify(rule!.Resource)).toContain(
    ":rule/DO-NOT-DELETE-AmazonGuardDutyMalwareProtectionS3*",
  );
});

test("there is a curators' topic, apart from the alert topic, and the ingest may publish to both", () => {
  const curators = logicalId(archive.curatorTopic);
  const alerts = logicalId(archive.alertTopic);
  expect(curators).not.toBe(alerts);
  template.hasResourceProperties("AWS::SNS::Topic", { DisplayName: "Research archive curators" });

  const publish = statements(INGEST).filter((s) => actions(s).includes("sns:Publish"));
  const topics = publish.map((s) => s.Resource);
  expect(topics).toContainEqual({ Ref: curators });
  expect(topics).toContainEqual({ Ref: alerts });
  expect(statements(SUBMISSIONS).some((s) => actions(s).includes("sns:Publish"))).toBe(false);
});

test("only the submissions function may send callbacks, scoped to the ingest function's executions", () => {
  // The ingest has a fixed name, so the submissions function names it without a reference.
  expect(fn(INGEST).properties.FunctionName).toBe("ResearchArchive-prod-Ingest");
  const callback = statements(SUBMISSIONS).filter((s) =>
    actions(s).includes("lambda:SendDurableExecutionCallbackSuccess"),
  );

  expect(callback).toHaveLength(1);
  expect(actions(callback[0]!)).toEqual(["lambda:SendDurableExecutionCallbackSuccess"]);
  expect(JSON.stringify(callback[0]!.Resource)).toMatch(
    /:function:ResearchArchive-prod-Ingest:\*"\]\]\}$/,
  );
  expect(
    statements(INGEST).some((s) =>
      actions(s).includes("lambda:SendDurableExecutionCallbackSuccess"),
    ),
  ).toBe(false);

  const invoke = statements(SUBMISSIONS).filter((s) =>
    actions(s).includes("lambda:InvokeFunction"),
  );
  expect(invoke).toHaveLength(1);
  expect(actions(invoke[0]!)).toEqual(["lambda:InvokeFunction"]);
  expect(JSON.stringify(invoke[0]!.Resource)).toMatch(
    /:function:ResearchArchive-prod-Ingest:live"\]\]\}$/,
  );
});

test("the ingest writes only the archive's open/ and restricted/ and the derived site's dataset pages", () => {
  const puts = statements(INGEST).filter((s) => actions(s).includes("s3:PutObject"));
  const resources = JSON.stringify(puts.map((s) => s.Resource));
  const archiveId = logicalId(archive.archiveBucket);
  const derivedId = logicalId(archive.derivedBucket);
  const stagingId = logicalId(archive.stagingBucket);

  for (const prefix of ["/open/*", "/restricted/*"]) expect(resources).toContain(prefix);
  expect(resources).toContain("/site/datasets/*");
  expect(resources).toContain("/held/*");
  expect(resources).toContain("/reports/*");
  for (const s of puts) {
    const r = JSON.stringify(s.Resource);
    if (r.includes(archiveId) || r.includes(derivedId) || r.includes(stagingId)) {
      expect(r).not.toMatch(/"\/\*"/);
    }
  }
});

test("the submissions function may read incoming/, so submit can HEAD each declared file", () => {
  const reads = statements(SUBMISSIONS).filter((s) => actions(s).includes("s3:GetObject"));
  const resources = JSON.stringify(reads.map((s) => s.Resource));

  expect(resources).toContain("/incoming/*");
  expect(resources).toContain("/reports/*");
  expect(resources).not.toMatch(/"\/\*"/);
});

test("the ingest may claim a version on either catalog table with a conditional update", () => {
  const updates = statements(INGEST).filter((s) => actions(s).includes("dynamodb:UpdateItem"));
  const resources = JSON.stringify(updates.map((s) => s.Resource));

  for (const table of [archive.catalogTables.a, archive.catalogTables.b]) {
    expect(resources).toContain(stack.getLogicalId(table.node.defaultChild as CfnBucket));
  }
});
