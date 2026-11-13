import { App, Stack } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import type { CfnBucket } from "aws-cdk-lib/aws-s3";
import { expect, test } from "vitest";
import type { Modules } from "../src/generated/archive-config";
import { ResearchArchive } from "../src/research-archive";

function archive(
  stage = "prod",
  modules: Modules = {},
): { archive: ResearchArchive; template: Template } {
  const stack = new Stack(new App(), "S");
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

test("staging objects expire after 30 days", () => {
  const { archive: a, template } = archive();
  const staging = template.toJSON().Resources[bucketOf(a, "stagingBucket")];

  expect(staging.Properties.LifecycleConfiguration.Rules).toEqual([
    expect.objectContaining({ ExpirationInDays: 30, Status: "Enabled" }),
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
