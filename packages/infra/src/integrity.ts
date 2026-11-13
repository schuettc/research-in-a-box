import { Duration } from "aws-cdk-lib";
import type * as s3 from "aws-cdk-lib/aws-s3";
import * as scheduler from "aws-cdk-lib/aws-scheduler";
import * as targets from "aws-cdk-lib/aws-scheduler-targets";
import type * as sns from "aws-cdk-lib/aws-sns";
import { Construct } from "constructs";
import type { ResearchArchive } from "./research-archive";

export interface IntegrityCheckProps {
  readonly archive: ResearchArchive;
  readonly archiveBucket: s3.IBucket;
  readonly alertTopic: sns.ITopic;
}

/**
 * The weekly check of every archived file against its package's checksums. It never retries
 * on its own: problems are reported, not raised, and a failed run alarms instead.
 */
export class IntegrityCheck extends Construct {
  constructor(scope: Construct, id: string, props: IntegrityCheckProps) {
    super(scope, id);
    const fn = props.archive.pythonFunction("IntegrityCheckFunction", {
      handler: "archive_backend.integrity.handler",
      timeout: Duration.minutes(15),
      environment: {
        ARCHIVE_BUCKET: props.archiveBucket.bucketName,
        ALERT_TOPIC_ARN: props.alertTopic.topicArn,
      },
    });
    props.archiveBucket.grantRead(fn);
    props.alertTopic.grantPublish(fn);
    fn.configureAsyncInvoke({ retryAttempts: 0 });

    new scheduler.Schedule(this, "Weekly", {
      schedule: scheduler.ScheduleExpression.rate(Duration.days(7)),
      target: new targets.LambdaInvoke(fn, { retryAttempts: 0 }),
    });
  }
}
