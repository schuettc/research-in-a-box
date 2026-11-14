import { type CfnElement, Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { beforeAll, expect, test } from "vitest";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

interface Built {
  stack: Stack;
  archive: ResearchArchive;
  template: Template;
}

function build(stage: string): Built {
  const stack = new Stack(testApp(), `S-${stage}`);
  const archive = new ResearchArchive(stack, "Archive", {
    config: {
      publisher: "P",
      infrastructure: { alertEmail: "a@example.org", stages: [{ name: stage }] },
    },
    stage,
  });
  return { stack, archive, template: Template.fromStack(stack) };
}

let prod: Built;
let dev: Built;

beforeAll(() => {
  prod = build("prod");
  dev = build("dev");
});

type Resource = { Properties: Record<string, unknown> };

function fn(handler: string): { id: string; properties: Record<string, unknown> } {
  const fns = prod.template.findResources("AWS::Lambda::Function", {
    Properties: { Handler: handler },
  });
  expect(Object.keys(fns)).toHaveLength(1);
  const [id, resource] = Object.entries(fns)[0] as [string, Resource];
  return { id, properties: resource.Properties };
}

function statements(handler: string): { Action: string | string[]; Resource: unknown }[] {
  const { id } = fn(handler);
  const resources = prod.template.toJSON().Resources;
  const role = (resources[id].Properties.Role as { "Fn::GetAtt": string[] })["Fn::GetAtt"][0];
  const policies = prod.template.findResources("AWS::IAM::Policy", {
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

function allows(handler: string, action: string, resource: unknown): boolean {
  const needle = JSON.stringify(resource);
  return statements(handler).some(
    (s) => actions(s).includes(action) && JSON.stringify(s.Resource).includes(needle),
  );
}

function ref(table: { node: { defaultChild?: unknown } }): unknown {
  return { "Fn::GetAtt": [prod.stack.getLogicalId(table.node.defaultChild as CfnElement), "Arn"] };
}

/** Every method on the REST API, as `<METHOD> <path>` mapped to its authorization type. */
function methods(): Record<string, string> {
  const resources = prod.template.toJSON().Resources as Record<
    string,
    { Type: string; Properties: Record<string, unknown> }
  >;
  const pathOf = (id: string | undefined): string => {
    if (!id || resources[id]?.Type !== "AWS::ApiGateway::Resource") return "";
    const props = resources[id].Properties;
    const parent = (props.ParentId as { Ref?: string }).Ref;
    return `${pathOf(parent)}/${props.PathPart as string}`;
  };
  const found: Record<string, string> = {};
  for (const resource of Object.values(resources)) {
    if (resource.Type !== "AWS::ApiGateway::Method") continue;
    const props = resource.Properties;
    const path = pathOf((props.ResourceId as { Ref?: string }).Ref);
    found[`${props.HttpMethod as string} ${path}`] = props.AuthorizationType as string;
  }
  return found;
}

const API = "archive_backend.api.handler";
const ROLLUP = "archive_backend.downloads.handler";

test("each route has its method and authorization type", () => {
  expect(methods()).toMatchObject({
    "GET /api/search": "NONE",
    "GET /api/datasets/{id}": "NONE",
    "GET /api/datasets/{id}/versions": "NONE",
    "GET /api/datasets/{id}/versions/{version}": "NONE",
    "GET /api/datasets/{id}/versions/{version}/download": "COGNITO_USER_POOLS",
    "POST /api/datasets/{id}/usage": "NONE",
    "GET /api/projects/{id}": "NONE",
    "GET /api/admin/usage": "COGNITO_USER_POOLS",
    "GET /api/health": "NONE",
    "GET /api/whoami": "COGNITO_USER_POOLS",
  });
});

test("the signed-in routes use the archive's authorizer", () => {
  const authorizerId = prod.stack.getLogicalId(
    prod.archive.authorizer.node.defaultChild as CfnElement,
  );
  const signedIn = prod.template.findResources("AWS::ApiGateway::Method", {
    Properties: { AuthorizationType: "COGNITO_USER_POOLS" },
  });
  // Which routes are signed in is pinned by the route table above; Plan 7 adds its own.
  expect(Object.keys(signedIn).length).toBeGreaterThanOrEqual(3);
  for (const method of Object.values(signedIn) as Resource[]) {
    expect(method.Properties.AuthorizerId).toEqual({ Ref: authorizerId });
  }
});

test("every read route goes to the one API function", () => {
  const { id } = fn(API);
  const integrations = (
    Object.values(prod.template.findResources("AWS::ApiGateway::Method")) as Resource[]
  )
    .map((m) => JSON.stringify(m.Properties.Integration))
    .filter((i) => i.includes(id));
  expect(integrations).toHaveLength(8);
});

test("the API function's environment names what it reads and writes", () => {
  expect(fn(API).properties).toMatchObject({
    Runtime: "python3.13",
    Architectures: ["arm64"],
    Environment: {
      Variables: {
        ARCHIVE_BUCKET: expect.anything(),
        DERIVED_BUCKET: expect.anything(),
        CATALOG_TABLE_A: expect.anything(),
        CATALOG_TABLE_B: expect.anything(),
        ACTIVE_CATALOG_PARAMETER: expect.anything(),
        DOWNLOAD_COUNTS_TABLE: expect.anything(),
        USAGE_TABLE: expect.anything(),
        SITE_DOMAIN_PARAMETER: "/research-archive/prod/site-domain",
      },
    },
  });
});

test("the site domain parameter holds the distribution's domain, and the API function may read it", () => {
  prod.template.hasResourceProperties("AWS::SSM::Parameter", {
    Name: "/research-archive/prod/site-domain",
    Value: {
      "Fn::GetAtt": [
        prod.stack.getLogicalId(prod.archive.distribution.node.defaultChild as CfnElement),
        "DomainName",
      ],
    },
  });
  const reads = statements(API).filter((s) => actions(s).includes("ssm:GetParameter"));
  expect(
    reads.some((s) =>
      JSON.stringify(s.Resource).includes(":parameter/research-archive/prod/site-domain"),
    ),
  ).toBe(true);
});

test("the API function may read the catalog and signed files, add counts and keep usage", () => {
  const { archive } = prod;
  for (const table of [archive.catalogTables.a, archive.catalogTables.b]) {
    expect(allows(API, "dynamodb:Query", ref(table))).toBe(true);
    expect(allows(API, "dynamodb:PutItem", ref(table))).toBe(false);
  }
  expect(allows(API, "dynamodb:UpdateItem", ref(archive.downloadCounts))).toBe(true);
  expect(allows(API, "dynamodb:PutItem", ref(archive.downloadCounts))).toBe(false);
  expect(allows(API, "dynamodb:PutItem", ref(archive.usageResponses))).toBe(true);
  expect(allows(API, "dynamodb:Query", ref(archive.usageResponses))).toBe(true);
  expect(statements(API).some((s) => actions(s).includes("ssm:GetParameter"))).toBe(true);
  const reads = statements(API)
    .filter((s) => actions(s).includes("s3:GetObject*"))
    .map((s) => JSON.stringify(s.Resource));
  expect(reads.some((r) => r.includes("/site/catalog.json"))).toBe(true);
  expect(reads.some((r) => r.includes("/restricted/*"))).toBe(true);
  expect(reads.some((r) => r.includes("/projects/*"))).toBe(true);
  expect(reads.some((r) => r.includes("/open/*") || r.includes('"/*"'))).toBe(false);
  expect(statements(API).some((s) => actions(s).includes("s3:PutObject"))).toBe(false);
});

test("UsageResponses is keyed by dataset and entry, on demand, with point-in-time recovery", () => {
  const props = {
    KeySchema: [
      { AttributeName: "datasetId", KeyType: "HASH" },
      { AttributeName: "entry", KeyType: "RANGE" },
    ],
    BillingMode: "PAY_PER_REQUEST",
    PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
  };
  prod.template.hasResource("AWS::DynamoDB::Table", {
    Properties: { ...props, DeletionProtectionEnabled: true },
    DeletionPolicy: "Retain",
  });
  dev.template.hasResource("AWS::DynamoDB::Table", {
    Properties: props,
    DeletionPolicy: "Delete",
  });
});

test("the download rollup runs daily with no retries, reading logs and writing counts and settings", () => {
  const { id, properties } = fn(ROLLUP);
  expect(properties).toMatchObject({
    Timeout: 900,
    Environment: {
      Variables: {
        DERIVED_BUCKET: expect.anything(),
        DOWNLOAD_COUNTS_TABLE: expect.anything(),
        SETTINGS_TABLE: expect.anything(),
      },
    },
  });
  prod.template.hasResourceProperties("AWS::Scheduler::Schedule", {
    ScheduleExpression: "rate(1 day)",
    Target: { Arn: { "Fn::GetAtt": [id, "Arn"] }, RetryPolicy: { MaximumRetryAttempts: 0 } },
  });
  prod.template.hasResourceProperties("AWS::Lambda::EventInvokeConfig", {
    FunctionName: { Ref: id },
    MaximumRetryAttempts: 0,
  });
  const { archive } = prod;
  expect(allows(ROLLUP, "dynamodb:UpdateItem", ref(archive.downloadCounts))).toBe(true);
  expect(allows(ROLLUP, "dynamodb:PutItem", ref(archive.settings))).toBe(true);
  expect(allows(ROLLUP, "dynamodb:GetItem", ref(archive.settings))).toBe(true);
  const reads = statements(ROLLUP)
    .filter((s) => actions(s).includes("s3:GetObject*"))
    .map((s) => JSON.stringify(s.Resource));
  expect(reads).toHaveLength(1);
  expect(reads[0]).toContain("/logs/*");
});

test("the API function knows its stage", () => {
  const env = (
    fn("archive_backend.api.handler").properties.Environment as {
      Variables: Record<string, unknown>;
    }
  ).Variables;

  expect(env.STAGE).toBe("prod");
});

test("without the embeddings module the API function has no Bedrock or SearchVectors grant", () => {
  const granted = statements("archive_backend.api.handler").flatMap(actions);

  expect(granted).not.toContain("bedrock:InvokeModel");
  expect(granted).not.toContain("dynamodb:SearchVectors");
});

test("with the embeddings module the API function may embed and search both vector indexes", () => {
  const stack = new Stack(testApp(), "E");
  const archive = new ResearchArchive(stack, "Archive", {
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
  const json = template.toJSON();
  const id = Object.keys(
    template.findResources("AWS::Lambda::Function", {
      Properties: { Handler: "archive_backend.api.handler" },
    }),
  )[0] as string;
  const role = json.Resources[id].Properties.Role["Fn::GetAtt"][0];
  const granted = Object.values(
    template.findResources("AWS::IAM::Policy", { Properties: { Roles: [{ Ref: role }] } }),
  ).flatMap(
    (p) =>
      (p as { Properties: { PolicyDocument: { Statement: never[] } } }).Properties.PolicyDocument
        .Statement,
  ) as { Action: string | string[]; Resource: unknown }[];

  const bedrock = granted.filter((s) => actions(s).includes("bedrock:InvokeModel"));
  expect(bedrock).toHaveLength(1);
  expect(JSON.stringify(bedrock.map((s) => s.Resource))).toContain(
    "::foundation-model/amazon.titan-embed-text-v2:0",
  );
  const vectors = granted.filter((s) => actions(s).includes("dynamodb:SearchVectors"));
  const tableArn = (table: CfnElement) => ({ "Fn::GetAtt": [stack.getLogicalId(table), "Arn"] });
  expect(vectors.map((s) => s.Resource)).toEqual([
    [archive.catalogTables.a, archive.catalogTables.b].map((t) => ({
      "Fn::Join": ["", [tableArn(t.node.defaultChild as CfnElement), "/index/datasets"]],
    })),
  ]);
});
