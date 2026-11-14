import { CfnOutput, Duration, Stack } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { Construct } from "constructs";
import type { ResearchArchive } from "./research-archive";

export interface ReindexProps {
  readonly archive: ResearchArchive;
}

/**
 * The reindex: a durable function that rebuilds the inactive catalog table from the archive's
 * manifests with a bulk load, then flips the active-catalog parameter to it.
 */
export class Reindex extends Construct {
  readonly alias: lambda.Alias;

  constructor(scope: Construct, id: string, props: ReindexProps) {
    super(scope, id);
    const { archive } = props;
    const tables = [archive.catalogTables.a, archive.catalogTables.b];
    const fn = archive.pythonFunction("ReindexFunction", {
      handler: "archive_backend.reindex.handler",
      timeout: Duration.minutes(15),
      memorySize: 1024,
      durableConfig: { executionTimeout: Duration.hours(12), retentionPeriod: Duration.days(30) },
      environment: {
        ARCHIVE_BUCKET: archive.archiveBucket.bucketName,
        DERIVED_BUCKET: archive.derivedBucket.bucketName,
        CATALOG_TABLE_A: archive.catalogTables.a.tableName,
        CATALOG_TABLE_B: archive.catalogTables.b.tableName,
        ACTIVE_CATALOG_PARAMETER: archive.activeCatalogParameter.parameterName,
        ALERT_TOPIC_ARN: archive.alertTopic.topicArn,
        ARCHIVE_CONFIG_PARAMETER: archive.archiveConfigParameter.parameterName,
      },
    });
    this.alias = new lambda.Alias(this, "Live", { aliasName: "live", version: fn.currentVersion });

    archive.archiveBucket.grantRead(fn);
    archive.derivedBucket.grantReadWrite(fn, "reindex/*");
    archive.derivedBucket.grantPut(fn, "site/catalog.json");
    for (const table of tables) {
      table.grantReadWriteData(fn);
    }
    archive.activeCatalogParameter.grantRead(fn);
    archive.activeCatalogParameter.grantWrite(fn);
    archive.archiveConfigParameter.grantRead(fn);
    archive.alertTopic.grantPublish(fn);
    if (archive.embeddings) {
      archive.grantEmbedding(fn);
    }
    // Starting a bulk operation is authorized on the account, not on a table.
    fn.addToRolePolicy(
      new iam.PolicyStatement({ actions: ["dynamodb:StartBulkOperation"], resources: ["*"] }),
    );
    fn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["dynamodb:BulkPutItems"],
        resources: tables.map((table) => table.tableArn),
      }),
    );
    // A bulk operation's ARN is account-scoped: arn:aws:dynamodb:<region>:<account>:bulk-operation/<id>.
    fn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["dynamodb:DescribeBulkOperation"],
        resources: [
          Stack.of(this).formatArn({
            service: "dynamodb",
            resource: "bulk-operation",
            resourceName: "*",
          }),
        ],
      }),
    );

    new CfnOutput(Stack.of(this), "ReindexFunction", {
      key: "ReindexFunction",
      value: this.alias.functionArn,
    });
  }
}
