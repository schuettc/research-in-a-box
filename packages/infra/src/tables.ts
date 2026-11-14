import { RemovalPolicy } from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";

export interface TablesProps {
  readonly stage: string;
  readonly isProd: boolean;
  /** Give each catalog table the `datasets` vector index, for the embeddings module. */
  readonly embeddings: boolean;
}

/** The vector index semantic search asks for the datasets nearest a query. */
export const VECTOR_INDEX = "datasets";

function key(name: string): dynamodb.Attribute {
  return { name, type: dynamodb.AttributeType.STRING };
}

/**
 * The catalog tables A and B, the parameter naming the active one, and one table per kind of
 * operational record. Plain `dynamodb.Table`, not `TableV2`: TableV2 synthesises a global
 * table, and bulk put items, which the reindex uses, does not support global tables.
 */
export class Tables extends Construct {
  readonly catalogTables: { readonly a: dynamodb.Table; readonly b: dynamodb.Table };
  readonly activeCatalogParameter: ssm.StringParameter;
  readonly submissions: dynamodb.Table;
  readonly reviews: dynamodb.Table;
  readonly settings: dynamodb.Table;
  readonly userProfiles: dynamodb.Table;
  readonly downloadCounts: dynamodb.Table;

  constructor(scope: Construct, id: string, props: TablesProps) {
    super(scope, id);
    const common: Partial<dynamodb.TableProps> = {
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      ...(props.isProd
        ? { removalPolicy: RemovalPolicy.RETAIN, deletionProtection: true }
        : { removalPolicy: RemovalPolicy.DESTROY }),
    };
    const operational: Partial<dynamodb.TableProps> = {
      ...common,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
    };

    const catalog = (tableId: string): dynamodb.Table => {
      const table = new dynamodb.Table(this, tableId, {
        ...common,
        partitionKey: key("PK"),
        sortKey: key("SK"),
      });
      table.addGlobalSecondaryIndex({
        indexName: "GSI1",
        partitionKey: key("GSI1PK"),
        sortKey: key("GSI1SK"),
        projectionType: dynamodb.ProjectionType.ALL,
      });
      if (props.embeddings) {
        // Only dataset items carry `embedding`, so only they are in the index.
        (table.node.defaultChild as dynamodb.CfnTable).vectorIndexes = [
          {
            indexName: VECTOR_INDEX,
            vectorAttribute: { attributeName: "embedding" },
            dimensions: 1024,
            distanceFunction: "COSINE",
            projection: { projectionType: "KEYS_ONLY" },
          },
        ];
      }
      return table;
    };
    this.catalogTables = { a: catalog("CatalogA"), b: catalog("CatalogB") };
    this.activeCatalogParameter = new ssm.StringParameter(this, "ActiveCatalog", {
      parameterName: `/research-archive/${props.stage}/catalog-active`,
      stringValue: "A",
    });

    this.submissions = new dynamodb.Table(this, "Submissions", {
      ...operational,
      partitionKey: key("submissionId"),
    });
    this.submissions.addGlobalSecondaryIndex({
      indexName: "byStatus",
      partitionKey: key("status"),
      sortKey: key("createdAt"),
    });
    this.submissions.addGlobalSecondaryIndex({
      indexName: "bySubmitter",
      partitionKey: key("submitter"),
      sortKey: key("createdAt"),
    });
    // eventKey is written as `<at>#<eventId>`.
    this.reviews = new dynamodb.Table(this, "Reviews", {
      ...operational,
      partitionKey: key("submissionId"),
      sortKey: key("eventKey"),
    });
    this.settings = new dynamodb.Table(this, "Settings", {
      ...operational,
      partitionKey: key("name"),
    });
    this.userProfiles = new dynamodb.Table(this, "UserProfiles", {
      ...operational,
      partitionKey: key("userId"),
    });
    this.downloadCounts = new dynamodb.Table(this, "DownloadCounts", {
      ...operational,
      partitionKey: key("datasetId"),
      sortKey: key("month"),
    });
  }
}
