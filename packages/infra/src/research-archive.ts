import { CfnOutput, Stack } from "aws-cdk-lib";
import type * as apigateway from "aws-cdk-lib/aws-apigateway";
import type * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import type * as cognito from "aws-cdk-lib/aws-cognito";
import type * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import type * as lambda from "aws-cdk-lib/aws-lambda";
import type * as s3 from "aws-cdk-lib/aws-s3";
import type * as sns from "aws-cdk-lib/aws-sns";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";
import { Api } from "./api";
import { Auth } from "./auth";
import { stagesOf } from "./config";
import type { ArchiveConfig } from "./generated/archive-config";
import { Ingest } from "./ingest";
import { IntegrityCheck } from "./integrity";
import { Operations } from "./operations";
import { makePythonFunction, type PythonFunctionProps } from "./python-function";
import { ReadApi } from "./read-api";
import { Reindex } from "./reindex";
import { Storage } from "./storage";
import { Tables } from "./tables";
import { Web } from "./web";

// The standard tier's limit on a parameter's value.
const MAX_CONFIG_BYTES = 4096;

/** The embeddings module's one model, as the contract's `Embeddings.model` allows. */
const EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0";

export interface ResearchArchiveProps {
  readonly config: ArchiveConfig;
  readonly stage: string;
}

export class ResearchArchive extends Construct {
  readonly isProd: boolean;
  /** Whether `infrastructure.modules.embeddings` switches semantic search on. */
  readonly embeddings: boolean;
  readonly stagingBucket: s3.Bucket;
  readonly archiveBucket: s3.Bucket;
  readonly derivedBucket: s3.Bucket;
  readonly catalogTables: { readonly a: dynamodb.Table; readonly b: dynamodb.Table };
  readonly activeCatalogParameter: ssm.StringParameter;
  /** The validated config as JSON: the one way a Lambda reads the archive config. */
  readonly archiveConfigParameter: ssm.StringParameter;
  readonly submissions: dynamodb.Table;
  readonly reviews: dynamodb.Table;
  readonly settings: dynamodb.Table;
  readonly userProfiles: dynamodb.Table;
  readonly downloadCounts: dynamodb.Table;
  /** The optional usage answers readers give before a download, one item per answer. */
  readonly usageResponses: dynamodb.Table;
  readonly alertTopic: sns.Topic;
  readonly userPool: cognito.UserPool;
  readonly userPoolClients: {
    readonly web: cognito.UserPoolClient;
    readonly cli: cognito.UserPoolClient;
  };
  readonly api: apigateway.RestApi;
  readonly authorizer: apigateway.CognitoUserPoolsAuthorizer;
  readonly distribution: cloudfront.Distribution;
  /** The reindex's `live` alias: durable functions are invoked only through a version or alias. */
  readonly reindexFunction: lambda.Alias;
  /** The ingest's `live` alias: one durable execution per submission, named by its id. */
  readonly ingestFunction: lambda.Alias;
  /** Curators subscribe by email, filtered on `audience` (their user id, or "all"). */
  readonly curatorTopic: sns.Topic;
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

    const configJson = JSON.stringify(props.config);
    const configBytes = Buffer.byteLength(configJson, "utf-8");
    if (configBytes > MAX_CONFIG_BYTES) {
      throw new Error(
        `archive config is ${configBytes} bytes as JSON; the SSM parameter holds at most ${MAX_CONFIG_BYTES}`,
      );
    }
    this.archiveConfigParameter = new ssm.StringParameter(this, "ArchiveConfig", {
      parameterName: `/research-archive/${props.stage}/archive-config`,
      stringValue: configJson,
      tier: ssm.ParameterTier.STANDARD,
    });

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

    this.embeddings = infrastructure.modules?.embeddings != null;
    const tables = new Tables(this, "Tables", {
      stage: props.stage,
      isProd: this.isProd,
      embeddings: this.embeddings,
    });
    this.catalogTables = tables.catalogTables;
    this.activeCatalogParameter = tables.activeCatalogParameter;
    this.submissions = tables.submissions;
    this.reviews = tables.reviews;
    this.settings = tables.settings;
    this.userProfiles = tables.userProfiles;
    this.downloadCounts = tables.downloadCounts;
    this.operations.addTables([
      this.catalogTables.a,
      this.catalogTables.b,
      this.submissions,
      this.reviews,
      this.settings,
      this.userProfiles,
      this.downloadCounts,
    ]);

    const auth = new Auth(this, "Auth", { stage: props.stage, isProd: this.isProd });
    this.userPool = auth.userPool;

    const api = new Api(this, "Api", {
      userPool: this.userPool,
      waf: infrastructure.modules?.waf ?? false,
      health: this.pythonFunction("HealthFunction", { handler: "archive_backend.health.handler" }),
      whoami: this.pythonFunction("WhoamiFunction", { handler: "archive_backend.whoami.handler" }),
    });
    this.api = api.restApi;
    this.operations.addApi(this.api);
    this.authorizer = api.authorizer;

    this.distribution = new Web(this, "Web", {
      derivedBucket: this.derivedBucket,
      archiveBucket: this.archiveBucket,
      restApi: this.api,
    }).distribution;
    this.operations.addDistribution(this.distribution);
    // just smoke, just seed, CI's smoke step and just ingest-e2e read it on every stage.
    new CfnOutput(Stack.of(this), "SiteDomain", {
      key: "SiteDomain",
      value: this.distribution.distributionDomainName,
    });
    this.userPoolClients = auth.addAppClients(this.distribution.distributionDomainName);
    if (!this.isProd) {
      auth.addTestClient();
    }

    new IntegrityCheck(this, "IntegrityCheck", {
      archive: this,
      archiveBucket: this.archiveBucket,
      alertTopic: this.alertTopic,
    });

    this.usageResponses = new ReadApi(this, "ReadApi", {
      archive: this,
      stage: props.stage,
    }).usageResponses;
    this.operations.addTables([this.usageResponses]);
    if (this.embeddings) {
      this.operations.addSemanticFallback(props.stage);
    }

    this.reindexFunction = new Reindex(this, "Reindex", { archive: this }).alias;

    const ingest = new Ingest(this, "Ingest", { archive: this, stage: props.stage });
    this.ingestFunction = ingest.alias;
    this.curatorTopic = ingest.curatorTopic;
  }

  /** Let the function call Titan Text Embeddings v2, the embeddings module's model. */
  grantEmbedding(fn: lambda.Function): void {
    fn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["bedrock:InvokeModel"],
        resources: [
          Stack.of(this).formatArn({
            service: "bedrock",
            account: "",
            resource: "foundation-model",
            resourceName: EMBEDDING_MODEL,
          }),
        ],
      }),
    );
  }

  /** A Python Lambda from archive-backend, built the way the archive's own are, with its alarm. */
  pythonFunction(id: string, props: PythonFunctionProps): lambda.Function {
    const fn = makePythonFunction(this, id, { ...props, isProd: this.isProd });
    this.operations.addFunction(fn);
    return fn;
  }
}
