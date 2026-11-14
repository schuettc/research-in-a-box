import { ArnFormat, CfnOutput, Duration, Size, Stack } from "aws-cdk-lib";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as guardduty from "aws-cdk-lib/aws-guardduty";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import type * as s3 from "aws-cdk-lib/aws-s3";
import * as sns from "aws-cdk-lib/aws-sns";
import { Construct } from "constructs";
import type { ResearchArchive } from "./research-archive";

export interface IngestProps {
  readonly archive: ResearchArchive;
  readonly stage: string;
}

const GUARDDUTY_PLAN_SERVICE = "malware-protection-plan.guardduty.amazonaws.com";

function objects(bucket: s3.IBucket, ...prefixes: string[]): string[] {
  return prefixes.map((prefix) => bucket.arnForObjects(`${prefix}*`));
}

function allow(actions: string[], resources: string[], conditions?: Record<string, unknown>) {
  return new iam.PolicyStatement({ actions, resources, conditions });
}

/**
 * The ingest pipeline: the durable `IngestFunction` (one execution per submission, from submit
 * to its end), the `SubmissionsFunction` behind `/api/submissions`, the curators' topic, and
 * GuardDuty Malware Protection on the staging bucket's `incoming/` prefix.
 */
export class Ingest extends Construct {
  readonly alias: lambda.Alias;
  readonly curatorTopic: sns.Topic;

  constructor(scope: Construct, id: string, props: IngestProps) {
    super(scope, id);
    const { archive } = props;
    const staging = archive.stagingBucket;
    const catalogTables = [archive.catalogTables.a, archive.catalogTables.b];

    // Each curator subscribes with a filter on `audience`: their user id, or "all".
    this.curatorTopic = new sns.Topic(this, "Curators", {
      displayName: "Research archive curators",
    });

    const catalogEnv = {
      ACTIVE_CATALOG_PARAMETER: archive.activeCatalogParameter.parameterName,
      CATALOG_TABLE_A: archive.catalogTables.a.tableName,
      CATALOG_TABLE_B: archive.catalogTables.b.tableName,
    };
    const recordEnv = {
      SUBMISSIONS_TABLE: archive.submissions.tableName,
      REVIEWS_TABLE: archive.reviews.tableName,
      SETTINGS_TABLE: archive.settings.tableName,
      STAGING_BUCKET: staging.bucketName,
    };

    // A fixed name: the submissions function names the ingest by string, not by reference. The
    // ingest's SITE_DOMAIN refers to the distribution, whose API origin refers to the stage that
    // deploys the submissions routes, so a reference back to the ingest would be a cycle.
    const functionName = `ResearchArchive-${props.stage}-Ingest`;
    const functionArn = Stack.of(this).formatArn({
      service: "lambda",
      resource: "function",
      resourceName: functionName,
      arnFormat: ArnFormat.COLON_RESOURCE_NAME,
    });
    const aliasArn = `${functionArn}:live`;

    const fn = archive.pythonFunction("IngestFunction", {
      functionName,
      handler: "archive_backend.ingest.handler",
      timeout: Duration.minutes(15),
      memorySize: 2048,
      // diagnose downloads the whole round to /tmp.
      ephemeralStorageSize: Size.gibibytes(10),
      durableConfig: { executionTimeout: Duration.days(365), retentionPeriod: Duration.days(30) },
      environment: {
        ...recordEnv,
        ...catalogEnv,
        CURATOR_TOPIC_ARN: this.curatorTopic.topicArn,
        ALERT_TOPIC_ARN: archive.alertTopic.topicArn,
        ARCHIVE_CONFIG_PARAMETER: archive.archiveConfigParameter.parameterName,
        ARCHIVE_BUCKET: archive.archiveBucket.bucketName,
        DERIVED_BUCKET: archive.derivedBucket.bucketName,
        SITE_DOMAIN: archive.distribution.distributionDomainName,
      },
    });
    this.alias = new lambda.Alias(this, "Live", { aliasName: "live", version: fn.currentVersion });

    // Scan reads the tags; check reads the round; hold copies it to held/; reports/ keeps the
    // diagnosis; reject, abandon, expire and publish empty held/.
    fn.addToRolePolicy(allow(["s3:GetObject"], objects(staging, "incoming/", "held/")));
    fn.addToRolePolicy(allow(["s3:GetObjectTagging"], objects(staging, "incoming/")));
    fn.addToRolePolicy(allow(["s3:PutObject"], objects(staging, "held/", "reports/")));
    // copy_object copies the source's scan tag, which needs PutObjectTagging on the copy.
    fn.addToRolePolicy(allow(["s3:PutObjectTagging"], objects(staging, "held/")));
    fn.addToRolePolicy(allow(["s3:DeleteObject"], objects(staging, "held/")));
    fn.addToRolePolicy(
      allow(["s3:ListBucket"], [staging.bucketArn], { StringLike: { "s3:prefix": "held/*" } }),
    );
    // Publish writes each file, then reads the manifest it just wrote for the page.
    fn.addToRolePolicy(
      allow(
        ["s3:PutObject", "s3:GetObject"],
        objects(archive.archiveBucket, "open/", "restricted/"),
      ),
    );
    fn.addToRolePolicy(allow(["s3:PutObject"], objects(archive.derivedBucket, "site/datasets/")));
    archive.submissions.grant(fn, "dynamodb:GetItem", "dynamodb:UpdateItem");
    archive.reviews.grant(fn, "dynamodb:PutItem");
    archive.settings.grant(fn, "dynamodb:GetItem");
    // Publish claims its version with a conditional update of the dataset item.
    for (const table of catalogTables) {
      table.grant(fn, "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:BatchWriteItem");
    }
    archive.activeCatalogParameter.grantRead(fn);
    archive.archiveConfigParameter.grantRead(fn);
    archive.alertTopic.grantPublish(fn);
    this.curatorTopic.grantPublish(fn);
    // Publish embeds the dataset item before its put.
    if (archive.embeddings) {
      archive.grantEmbedding(fn);
    }

    const api = archive.pythonFunction("SubmissionsFunction", {
      handler: "archive_backend.submissions.handler",
      environment: { ...recordEnv, ...catalogEnv, INGEST_ALIAS_ARN: aliasArn },
    });
    // Presigned PUTs are signed with the function's own role, so it needs the PUT itself.
    api.addToRolePolicy(allow(["s3:PutObject"], objects(staging, "incoming/")));
    // Submit HEADs each declared file in incoming/; read presigns the report.
    api.addToRolePolicy(allow(["s3:GetObject"], objects(staging, "incoming/", "reports/")));
    archive.submissions.grant(
      api,
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    );
    archive.reviews.grant(api, "dynamodb:PutItem", "dynamodb:Query");
    archive.settings.grant(api, "dynamodb:GetItem", "dynamodb:PutItem");
    for (const table of catalogTables) {
      table.grant(api, "dynamodb:GetItem");
    }
    archive.activeCatalogParameter.grantRead(api);
    api.addToRolePolicy(allow(["lambda:InvokeFunction"], [aliasArn]));
    // Lambda authorizes a callback against the ARN of the execution that opened it, which sits
    // under the function's qualified ARN.
    api.addToRolePolicy(
      allow(["lambda:SendDurableExecutionCallbackSuccess"], [`${functionArn}:*`]),
    );

    const integration = new apigateway.LambdaIntegration(api);
    const auth: apigateway.MethodOptions = {
      authorizationType: apigateway.AuthorizationType.COGNITO,
      authorizer: archive.authorizer,
    };
    const submissions = archive.api.root.getResource("api")!.addResource("submissions");
    submissions.addMethod("POST", integration, auth);
    submissions.addMethod("GET", integration, auth);
    const policy = submissions.addResource("policy");
    policy.addMethod("GET", integration, auth);
    policy.addMethod("PUT", integration, auth);
    const one = submissions.addResource("{id}");
    one.addMethod("GET", integration, auth);
    for (const action of ["uploads", "submit", "decision"]) {
      one.addResource(action).addMethod("POST", integration, auth);
    }

    this.addMalwareProtection(staging);

    new CfnOutput(Stack.of(this), "IngestFunction", {
      key: "IngestFunction",
      value: this.alias.functionArn,
    });
    new CfnOutput(Stack.of(this), "CuratorTopic", {
      key: "CuratorTopic",
      value: this.curatorTopic.topicArn,
    });
  }

  /**
   * GuardDuty Malware Protection for S3 on `incoming/`, tagging each scanned object with
   * `GuardDutyMalwareScanStatus`. The role is AWS's documented template, with the object
   * actions narrowed to the scanned prefix. The bucket is SSE-S3, so no KMS statement.
   */
  private addMalwareProtection(staging: s3.IBucket): void {
    const stack = Stack.of(this);
    const managedRule = stack.formatArn({
      service: "events",
      resource: "rule",
      resourceName: "DO-NOT-DELETE-AmazonGuardDutyMalwareProtectionS3*",
    });
    const role = new iam.Role(this, "MalwareProtectionRole", {
      assumedBy: new iam.ServicePrincipal(GUARDDUTY_PLAN_SERVICE),
      inlinePolicies: {
        MalwareProtection: new iam.PolicyDocument({
          statements: [
            allow(
              ["events:PutRule", "events:DeleteRule", "events:PutTargets", "events:RemoveTargets"],
              [managedRule],
              { StringLike: { "events:ManagedBy": GUARDDUTY_PLAN_SERVICE } },
            ),
            allow(["events:DescribeRule", "events:ListTargetsByRule"], [managedRule]),
            allow(
              [
                "s3:PutObjectTagging",
                "s3:GetObjectTagging",
                "s3:PutObjectVersionTagging",
                "s3:GetObjectVersionTagging",
              ],
              objects(staging, "incoming/"),
            ),
            allow(["s3:PutBucketNotification", "s3:GetBucketNotification"], [staging.bucketArn]),
            allow(
              ["s3:PutObject"],
              [staging.arnForObjects("malware-protection-resource-validation-object")],
            ),
            allow(["s3:ListBucket"], [staging.bucketArn]),
            allow(["s3:GetObject", "s3:GetObjectVersion"], objects(staging, "incoming/")),
          ],
        }),
      },
    });
    new guardduty.CfnMalwareProtectionPlan(this, "MalwareProtection", {
      role: role.roleArn,
      protectedResource: {
        s3Bucket: { bucketName: staging.bucketName, objectPrefixes: ["incoming/"] },
      },
      actions: { tagging: { status: "ENABLED" } },
    });
  }
}
