import { Duration, RemovalPolicy } from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface StorageProps {
  readonly isProd: boolean;
  readonly objectLock?: { readonly retentionDays: number };
}

/**
 * The staging, archive and derived buckets. The archive bucket keeps open data under `open/`
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
      lifecycleRules: [{ expiration: Duration.days(30) }],
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
}
