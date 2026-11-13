import type * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import type * as lambda from "aws-cdk-lib/aws-lambda";
import type * as s3 from "aws-cdk-lib/aws-s3";
import type * as sns from "aws-cdk-lib/aws-sns";
import type * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";
import { stagesOf } from "./config";
import type { ArchiveConfig } from "./generated/archive-config";
import { Operations } from "./operations";
import { makePythonFunction, type PythonFunctionProps } from "./python-function";
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
  readonly alertTopic: sns.Topic;
  private readonly operations: Operations;

  constructor(scope: Construct, id: string, props: ResearchArchiveProps) {
    super(scope, id);
    if (!stagesOf(props.config).some((stage) => stage.name === props.stage)) {
      throw new Error(`stage "${props.stage}" is not in infrastructure.stages`);
    }
    this.isProd = props.stage === "prod";
    const infrastructure = props.config.infrastructure;
    if (!infrastructure) {
      throw new Error("ResearchArchive needs config.infrastructure");
    }

    this.operations = new Operations(this, "Operations", {
      stage: props.stage,
      alertEmail: infrastructure.alertEmail,
      monthlyBudgetUsd: infrastructure.monthlyBudgetUsd ?? 50,
    });
    this.alertTopic = this.operations.alertTopic;

    const objectLock = infrastructure.modules?.objectLock ?? undefined;
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

  /** A Python Lambda from archive-backend, built the way the archive's own are, with its alarm. */
  pythonFunction(id: string, props: PythonFunctionProps): lambda.Function {
    const fn = makePythonFunction(this, id, { ...props, isProd: this.isProd });
    this.operations.addFunction(fn);
    return fn;
  }
}
