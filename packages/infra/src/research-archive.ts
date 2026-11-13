import type * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";
import { stagesOf } from "./config";
import type { ArchiveConfig } from "./generated/archive-config";
import { Storage } from "./storage";

export interface ResearchArchiveProps {
  readonly config: ArchiveConfig;
  readonly stage: string;
}

export class ResearchArchive extends Construct {
  readonly isProd: boolean;
  readonly stagingBucket: s3.Bucket;
  readonly archiveBucket: s3.Bucket;
  readonly derivedBucket: s3.Bucket;

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
  }
}
