import { Duration, RemovalPolicy } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as cr from "aws-cdk-lib/custom-resources";
import { Construct } from "constructs";

export interface StorageProps {
  readonly isProd: boolean;
  readonly objectLock?: { readonly retentionDays: number };
}

/**
 * The staging, archive and derived buckets. The staging bucket takes uploads under `incoming/`,
 * keeps rounds that passed the checks under `held/` and diagnoses under `reports/`. The archive bucket keeps open data under `open/`
 * and restricted data under `restricted/`; the derived bucket holds `site/`, `reindex/` and
 * `logs/`. Those prefixes are conventions, not resources.
 */
export class Storage extends Construct {
  readonly stagingBucket: s3.Bucket;
  readonly archiveBucket: s3.Bucket;
  readonly derivedBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props: StorageProps) {
    super(scope, id);
    const common: s3.BucketProps = {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      encryption: s3.BucketEncryption.S3_MANAGED,
      ...(props.isProd
        ? { removalPolicy: RemovalPolicy.RETAIN }
        : { removalPolicy: RemovalPolicy.DESTROY, autoDeleteObjects: true }),
    };

    this.stagingBucket = new s3.Bucket(this, "Staging", {
      ...common,
      // Only uploads expire: held/ and reports/ stay until publish, reject or abandon removes them.
      lifecycleRules: [{ prefix: "incoming/", expiration: Duration.days(30) }],
    });
    this.archiveBucket = new s3.Bucket(this, "Archive", {
      ...common,
      versioned: true,
      ...(props.objectLock && {
        objectLockEnabled: true,
        objectLockDefaultRetention: s3.ObjectLockRetention.governance(
          Duration.days(props.objectLock.retentionDays),
        ),
      }),
    });
    // CloudFront delivers standard logs with an ACL, which a bucket enforcing the owner refuses.
    this.derivedBucket = new s3.Bucket(this, "Derived", {
      ...common,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
    });
  }

  /**
   * Let the web app's origins PUT presigned uploads to the staging bucket and GET its reports
   * and held files. Applied by a PutBucketCors call rather than the bucket's own CORS property:
   * the distribution's API origin depends, through the submissions function, on this bucket, so
   * the bucket can't name the distribution's domain without a CloudFormation cycle.
   */
  allowStagingOrigins(origins: string[]): void {
    const call: cr.AwsSdkCall = {
      service: "S3",
      action: "putBucketCors",
      parameters: {
        Bucket: this.stagingBucket.bucketName,
        CORSConfiguration: {
          CORSRules: [
            {
              AllowedOrigins: origins,
              AllowedMethods: ["PUT", "GET"],
              AllowedHeaders: ["x-amz-checksum-sha256", "content-type", "range"],
              ExposeHeaders: ["ETag"],
              MaxAgeSeconds: 3600,
            },
          ],
        },
      },
      physicalResourceId: cr.PhysicalResourceId.of(`${this.node.path}/StagingCors`),
    };
    new cr.AwsCustomResource(this, "StagingCors", {
      onCreate: call,
      onUpdate: call,
      installLatestAwsSdk: false,
      policy: cr.AwsCustomResourcePolicy.fromStatements([
        new iam.PolicyStatement({
          actions: ["s3:PutBucketCORS"],
          resources: [this.stagingBucket.bucketArn],
        }),
      ]),
    });
  }
}
