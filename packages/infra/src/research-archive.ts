import type * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import type * as s3 from "aws-cdk-lib/aws-s3";
import type * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";
import { stagesOf } from "./config";
import type { ArchiveConfig } from "./generated/archive-config";
import { Storage } from "./storage";
import { Tables } from "./tables";

export interface ResearchArchiveProps {
  readonly config: ArchiveConfig;
  readonly stage: string;
}

export class ResearchArchive extends Construct {
  readonly isProd: boolean;
  readonly stagingBucket: s3.Bucket;
  readonly archiveBucket: s3.Bucket;
  readonly derivedBucket: s3.Bucket;
  readonly catalogTables: { readonly a: dynamodb.Table; readonly b: dynamodb.Table };
  readonly activeCatalogParameter: ssm.StringParameter;
  readonly submissions: dynamodb.Table;
  readonly reviews: dynamodb.Table;
  readonly settings: dynamodb.Table;
  readonly userProfiles: dynamodb.Table;
  readonly downloadCounts: dynamodb.Table;

  constructor(scope: Construct, id: string, props: ResearchArchiveProps) {
    super(scope, id);
    if (!stagesOf(props.config).some((stage) => stage.name === props.stage)) {
      throw new Error(`stage "${props.stage}" is not in infrastructure.stages`);
    }
    this.isProd = props.stage === "prod";

    const objectLock = props.config.infrastructure?.modules?.objectLock ?? undefined;
    const storage = new Storage(this, "Storage", { isProd: this.isProd, objectLock });
    this.stagingBucket = storage.stagingBucket;
    this.archiveBucket = storage.archiveBucket;
    this.derivedBucket = storage.derivedBucket;

    const tables = new Tables(this, "Tables", { stage: props.stage, isProd: this.isProd });
    this.catalogTables = tables.catalogTables;
    this.activeCatalogParameter = tables.activeCatalogParameter;
    this.submissions = tables.submissions;
    this.reviews = tables.reviews;
    this.settings = tables.settings;
    this.userProfiles = tables.userProfiles;
    this.downloadCounts = tables.downloadCounts;
  }
}
