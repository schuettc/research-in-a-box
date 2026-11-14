import { Stack } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import type { CfnBucket } from "aws-cdk-lib/aws-s3";
import { expect, test } from "vitest";
import type { Modules } from "../src/generated/archive-config";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

function archive(
  stage = "prod",
  modules: Modules = {},
): { archive: ResearchArchive; template: Template } {
  const stack = new Stack(testApp(), "S");
  const built = new ResearchArchive(stack, "Archive", {
    config: {
      publisher: "P",
      infrastructure: {
        alertEmail: "a@example.org",
        stages: [{ name: "prod" }, { name: "dev" }],
        modules,
      },
    },
    stage,
  });
  return { archive: built, template: Template.fromStack(stack) };
}

function bucketOf(a: ResearchArchive, which: "stagingBucket" | "archiveBucket" | "derivedBucket") {
  return Stack.of(a).getLogicalId(a[which].node.defaultChild as CfnBucket);
}

test("the archive bucket is versioned, blocks public access and enforces TLS", () => {
  const { archive: a, template } = archive();
  const id = bucketOf(a, "archiveBucket");
  const bucket = template.toJSON().Resources[id];

  expect(bucket.Properties).toMatchObject({
    VersioningConfiguration: { Status: "Enabled" },
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
    BucketEncryption: {
      ServerSideEncryptionConfiguration: [
        { ServerSideEncryptionByDefault: { SSEAlgorithm: "AES256" } },
      ],
    },
  });
  template.hasResourceProperties("AWS::S3::BucketPolicy", {
    Bucket: { Ref: id },
    PolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({
          Effect: "Deny",
          Condition: { Bool: { "aws:SecureTransport": "false" } },
        }),
      ]),
    },
  });
  expect(
    template.toJSON().Resources[bucketOf(a, "derivedBucket")].Properties.VersioningConfiguration,
  ).toBeUndefined();
});

test("only staging's incoming/ objects expire after 30 days", () => {
  const { archive: a, template } = archive();
  const staging = template.toJSON().Resources[bucketOf(a, "stagingBucket")];

  expect(staging.Properties.LifecycleConfiguration.Rules).toEqual([
    expect.objectContaining({ ExpirationInDays: 30, Prefix: "incoming/", Status: "Enabled" }),
  ]);
});

test("prod buckets are retained and a dev stage's are deleted with their objects", () => {
  const prod = archive("prod").template;
  const dev = archive("dev").template;

  const prodBuckets = Object.values(prod.findResources("AWS::S3::Bucket"));
  expect(prodBuckets).toHaveLength(3);
  for (const bucket of prodBuckets) {
    expect(bucket.DeletionPolicy).toBe("Retain");
  }
  expect(prod.findResources("Custom::S3AutoDeleteObjects")).toEqual({});

  const devBuckets = Object.values(dev.findResources("AWS::S3::Bucket"));
  expect(devBuckets).toHaveLength(3);
  for (const bucket of devBuckets) {
    expect(bucket.DeletionPolicy).toBe("Delete");
  }
  expect(Object.keys(dev.findResources("Custom::S3AutoDeleteObjects"))).toHaveLength(3);
});

test("write-once locking appears only when objectLock is set, in governance mode with its retention days", () => {
  const off = archive("prod", { objectLock: null }).template;
  for (const bucket of Object.values(off.findResources("AWS::S3::Bucket"))) {
    expect(bucket.Properties.ObjectLockEnabled).toBeUndefined();
    expect(bucket.Properties.ObjectLockConfiguration).toBeUndefined();
  }

  const { archive: a, template } = archive("prod", { objectLock: { retentionDays: 3650 } });
  const locked = Object.entries(template.findResources("AWS::S3::Bucket")).filter(
    ([, bucket]) => bucket.Properties.ObjectLockEnabled,
  );
  expect(locked.map(([id]) => id)).toEqual([bucketOf(a, "archiveBucket")]);
  expect(locked[0]?.[1].Properties.ObjectLockConfiguration).toEqual({
    ObjectLockEnabled: "Enabled",
    Rule: { DefaultRetention: { Mode: "GOVERNANCE", Days: 3650 } },
  });
});

function stagingCors(stage: string) {
  const { archive: a, template } = archive(stage);
  const calls = Object.values(template.findResources("Custom::AWS"));
  const cors = calls.filter((r) => JSON.stringify(r.Properties.Create).includes("putBucketCors"));
  expect(cors).toHaveLength(1);
  // The call is a JSON string joined around the bucket's and the distribution's tokens.
  const create = JSON.stringify(cors[0]!.Properties.Create);
  expect(JSON.stringify(cors[0]!.Properties.Update)).toEqual(create);
  return { a, create };
}

test("the staging bucket lets the site's origin PUT uploads and GET reports and held files", () => {
  const { a, create } = stagingCors("prod");
  const stack = Stack.of(a);
  const distribution = stack.getLogicalId(a.distribution.node.defaultChild as CfnBucket);

  expect(create).toContain(JSON.stringify({ Ref: bucketOf(a, "stagingBucket") }));
  expect(create).toContain(JSON.stringify({ "Fn::GetAtt": [distribution, "DomainName"] }));
  for (const part of [
    '\\"AllowedMethods\\":[\\"PUT\\",\\"GET\\"]',
    '\\"AllowedHeaders\\":[\\"x-amz-checksum-sha256\\",\\"content-type\\",\\"range\\"]',
    '\\"ExposeHeaders\\":[\\"ETag\\"]',
    '\\"AllowedOrigins\\":[\\"https://',
  ]) {
    expect(create).toContain(part);
  }
  expect(create).not.toContain("localhost");
});

test("a non-prod stage's staging bucket also allows the local web app", () => {
  const { create } = stagingCors("dev");

  expect(create).toContain('\\"http://localhost:5199\\"');
});

test("the CORS call may set only the staging bucket's CORS", () => {
  const { archive: a, template } = archive();
  const statements = Object.values(template.findResources("AWS::IAM::Policy")).flatMap(
    (p) => p.Properties.PolicyDocument.Statement as { Action: unknown; Resource: unknown }[],
  );
  const cors = statements.filter((s) => JSON.stringify(s.Action).includes("PutBucketCORS"));

  expect(cors).toEqual([
    expect.objectContaining({
      Action: "s3:PutBucketCORS",
      Resource: { "Fn::GetAtt": [bucketOf(a, "stagingBucket"), "Arn"] },
    }),
  ]);
});
