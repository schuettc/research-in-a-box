import { Stack } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import type { CfnRestApi } from "aws-cdk-lib/aws-apigateway";
import type { CfnDistribution } from "aws-cdk-lib/aws-cloudfront";
import type { CfnUserPoolClient } from "aws-cdk-lib/aws-cognito";
import type { CfnBucket } from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import { afterEach, expect, test, vi } from "vitest";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

function archive(): { archive: ResearchArchive; stack: Stack; template: Template } {
  const stack = new Stack(testApp(), "S");
  const built = new ResearchArchive(stack, "Archive", {
    config: {
      publisher: "P",
      infrastructure: { alertEmail: "a@example.org", stages: [{ name: "prod" }] },
    },
    stage: "prod",
  });
  return { archive: built, stack, template: Template.fromStack(stack) };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = Record<string, any>;

function distributionConfig(a: ResearchArchive, stack: Stack, template: Template): Json {
  const id = stack.getLogicalId(a.distribution.node.defaultChild as CfnDistribution);
  return template.toJSON().Resources[id].Properties.DistributionConfig as Json;
}

function bucketId(stack: Stack, bucket: ResearchArchive["archiveBucket"]): string {
  return stack.getLogicalId(bucket.node.defaultChild as CfnBucket);
}

function originOf(config: Json, originId: string): Json {
  const origin = (config.Origins as Json[]).find((o) => o.Id === originId);
  if (!origin) throw new Error(`no origin ${originId}`);
  return origin;
}

function functionCode(template: Template, arn: Json): string {
  const id = arn["Fn::GetAtt"][0] as string;
  return template.toJSON().Resources[id].Properties.FunctionCode as string;
}

/** Run a CloudFront Function's source on a request URI and return the rewritten URI. */
function rewrite(code: string, uri: string): string {
  const handler = new Function(`${code}; return handler;`)() as (event: Json) => Json;
  return handler({ request: { uri } }).uri as string;
}

test("the default behaviour serves site/ from the derived bucket through origin access control", () => {
  const { archive: a, stack, template } = archive();
  const config = distributionConfig(a, stack, template);
  const behaviour = config.DefaultCacheBehavior as Json;
  const origin = originOf(config, behaviour.TargetOriginId);

  expect(origin.DomainName["Fn::GetAtt"]).toEqual([
    bucketId(stack, a.derivedBucket),
    "RegionalDomainName",
  ]);
  expect(origin.OriginPath).toBe("/site");
  expect(origin.OriginAccessControlId).toBeDefined();
  expect(config.DefaultRootObject).toBe("index.html");
  expect(behaviour.ViewerProtocolPolicy).toBe("redirect-to-https");
  expect(behaviour.CachePolicyId).toBe("658327ea-f89d-4fab-a63d-7e88639e58f6");

  const [association] = behaviour.FunctionAssociations as Json[];
  expect(association?.EventType).toBe("viewer-request");
  const code = functionCode(template, association?.FunctionARN);
  expect(rewrite(code, "/docs/")).toBe("/docs/index.html");
  expect(rewrite(code, "/assets/app.js")).toBe("/assets/app.js");
});

test("the site function sends /datasets/<id> to its page and other extensionless paths to the app", () => {
  const { archive: a, stack, template } = archive();
  const behaviour = distributionConfig(a, stack, template).DefaultCacheBehavior as Json;
  const code = functionCode(template, (behaviour.FunctionAssociations as Json[])[0]?.FunctionARN);

  expect(rewrite(code, "/")).toBe("/index.html");
  expect(rewrite(code, "/about")).toBe("/index.html");
  expect(rewrite(code, "/datasets/abc")).toBe("/datasets/abc/index.html");
  expect(rewrite(code, "/datasets/abc/")).toBe("/datasets/abc/index.html");
  expect(rewrite(code, "/app.js")).toBe("/app.js");
});

test("the site function sends /datasets/<id>/v<n> to that version's page", () => {
  const { archive: a, stack, template } = archive();
  const behaviour = distributionConfig(a, stack, template).DefaultCacheBehavior as Json;
  const code = functionCode(template, (behaviour.FunctionAssociations as Json[])[0]?.FunctionARN);

  expect(rewrite(code, "/datasets/x/v2")).toBe("/datasets/x/v2/index.html");
  expect(rewrite(code, "/datasets/x/v2/")).toBe("/datasets/x/v2/index.html");
  expect(rewrite(code, "/datasets/x")).toBe("/datasets/x/index.html");
  expect(rewrite(code, "/datasets/x/other")).toBe("/index.html");
  expect(rewrite(code, "/datasets/x/v2/extra")).toBe("/index.html");
});

test("/data/* serves open/ from the archive bucket and strips /data", () => {
  const { archive: a, stack, template } = archive();
  const config = distributionConfig(a, stack, template);
  const behaviour = (config.CacheBehaviors as Json[]).find((b) => b.PathPattern === "/data/*");
  const origin = originOf(config, behaviour?.TargetOriginId);

  expect(origin.DomainName["Fn::GetAtt"][0]).toBe(bucketId(stack, a.archiveBucket));
  expect(origin.OriginPath).toBe("/open");
  expect(origin.OriginAccessControlId).toBeDefined();
  expect(behaviour?.AllowedMethods).toEqual(["GET", "HEAD"]);
  expect(behaviour?.CachePolicyId).toBe("658327ea-f89d-4fab-a63d-7e88639e58f6");
  const code = functionCode(template, behaviour?.FunctionAssociations[0].FunctionARN);
  expect(rewrite(code, "/data/ds-1/2/data/a.csv")).toBe("/ds-1/2/data/a.csv");
});

test("/api/* goes to the REST API uncached with all methods", () => {
  const { archive: a, stack, template } = archive();
  const config = distributionConfig(a, stack, template);
  const behaviour = (config.CacheBehaviors as Json[]).find((b) => b.PathPattern === "/api/*");
  const origin = originOf(config, behaviour?.TargetOriginId);
  const restApiId = stack.getLogicalId(a.api.node.defaultChild as CfnRestApi);

  expect(JSON.stringify(origin.DomainName)).toContain(restApiId);
  expect(behaviour?.AllowedMethods).toHaveLength(7);
  expect(behaviour?.CachePolicyId).toBe("4135ea2d-6df8-44a3-9df3-4b5a84be39ad");
  expect(behaviour?.OriginRequestPolicyId).toBe("b689b0a8-53d0-40ab-baf2-68738e2966ac");
});

test("the distribution has no error responses", () => {
  const { archive: a, stack, template } = archive();

  expect(distributionConfig(a, stack, template).CustomErrorResponses).toBeUndefined();
});

test("standard logs go to the derived bucket under logs/, and the derived bucket accepts the log ACL", () => {
  const { archive: a, stack, template } = archive();
  const derived = bucketId(stack, a.derivedBucket);

  expect(distributionConfig(a, stack, template).Logging).toEqual({
    Bucket: { "Fn::GetAtt": [derived, "RegionalDomainName"] },
    Prefix: "logs/",
  });
  expect(template.toJSON().Resources[derived].Properties).toMatchObject({
    OwnershipControls: { Rules: [{ ObjectOwnership: "BucketOwnerPreferred" }] },
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
  });
});

test("the web client's callback is on the distribution's domain", () => {
  const { archive: a, stack, template } = archive();
  const distribution = stack.getLogicalId(a.distribution.node.defaultChild as CfnDistribution);
  const web = stack.getLogicalId(a.userPoolClients.web.node.defaultChild as CfnUserPoolClient);
  const domain = { "Fn::GetAtt": [distribution, "DomainName"] };

  expect(template.toJSON().Resources[web].Properties).toMatchObject({
    CallbackURLs: [{ "Fn::Join": ["", ["https://", domain, "/auth/callback"]] }],
    LogoutURLs: [{ "Fn::Join": ["", ["https://", domain, "/"]] }],
  });
  template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
    CallbackURLs: ["http://localhost:8765/callback"],
    UserPoolId: Match.anyValue(),
  });
});

test("the SiteDomain output names the distribution's domain, for just smoke and just seed", () => {
  const { archive: a, stack, template } = archive();
  const distribution = stack.getLogicalId(a.distribution.node.defaultChild as CfnDistribution);

  template.hasOutput("SiteDomain", { Value: { "Fn::GetAtt": [distribution, "DomainName"] } });
});

test("CloudFront is denied the archive bucket's restricted/ prefix", () => {
  const { archive: a, stack, template } = archive();
  const policies = template.findResources("AWS::S3::BucketPolicy");
  const archivePolicy = Object.values(policies).find(
    (p) => (p as Json).Properties.Bucket.Ref === bucketId(stack, a.archiveBucket),
  ) as Json;
  const statements = archivePolicy.Properties.PolicyDocument.Statement as Json[];
  const deny = statements.find(
    (s) => s.Effect === "Deny" && s.Principal?.Service === "cloudfront.amazonaws.com",
  );

  expect(deny).toBeDefined();
  expect(deny?.Action).toBe("s3:GetObject");
  expect(JSON.stringify(deny?.Resource)).toContain("/restricted/*");
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** The bucket deployments writing into the derived bucket's site/. */
function siteDeployments(a: ResearchArchive, stack: Stack, template: Template): Json[] {
  const derived = bucketId(stack, a.derivedBucket);
  return Object.values(template.findResources("Custom::CDKBucketDeployment"))
    .map((resource) => (resource as Json).Properties as Json)
    .filter(
      (p) =>
        JSON.stringify(p.DestinationBucketName).includes(derived) &&
        String(p.DestinationBucketKeyPrefix ?? "").startsWith("site"),
    );
}

test("the app is deployed into site/ by two deployments that never prune", () => {
  const { archive: a, stack, template } = archive();
  const deployments = siteDeployments(a, stack, template);

  expect(deployments).toHaveLength(2);
  for (const deployment of deployments) {
    expect(deployment.Prune).toBe(false);
    expect(deployment.DestinationBucketKeyPrefix).toBe("site/");
  }
  const caching = deployments.map((d) => d.SystemMetadata?.["cache-control"]).sort();
  expect(caching).toEqual(["no-cache", "public, max-age=31536000, immutable"]);
});

test("the no-cache deployment writes auth-config.json and invalidates the app's stable files", () => {
  const { archive: a, stack, template } = archive();
  const distribution = stack.getLogicalId(a.distribution.node.defaultChild as CfnDistribution);
  const site = siteDeployments(a, stack, template).find(
    (d) => d.SystemMetadata?.["cache-control"] === "no-cache",
  );

  expect(site?.DistributionId).toEqual({ Ref: distribution });
  expect(site?.DistributionPaths).toEqual(["/index.html", "/app.js", "/auth-config.json"]);
  expect(site?.SourceObjectKeys).toHaveLength(2);
});

test("auth-config.json holds exactly the region, sign-in domain and both client ids", () => {
  const jsonData = vi.spyOn(s3deploy.Source, "jsonData");
  const { archive: a, stack } = archive();

  const call = jsonData.mock.calls.find(([name]) => name === "auth-config.json");
  expect(call).toBeDefined();
  const data = call?.[1] as Json;
  expect(Object.keys(data).sort()).toEqual([
    "cliClientId",
    "cognitoDomain",
    "region",
    "webClientId",
  ]);
  const ref = (client: { node: { defaultChild: unknown } }) => ({
    Ref: stack.getLogicalId(client.node.defaultChild as CfnUserPoolClient),
  });
  expect(stack.resolve(data.webClientId)).toEqual(ref(a.userPoolClients.web));
  expect(stack.resolve(data.cliClientId)).toEqual(ref(a.userPoolClients.cli));
  expect(stack.resolve(data.region)).toEqual({ Ref: "AWS::Region" });
  expect(JSON.stringify(stack.resolve(data.cognitoDomain))).toContain("amazoncognito.com");
});
