import { Duration } from "aws-cdk-lib";
import type * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as budgets from "aws-cdk-lib/aws-budgets";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as actions from "aws-cdk-lib/aws-cloudwatch-actions";
import type * as lambda from "aws-cdk-lib/aws-lambda";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subscriptions from "aws-cdk-lib/aws-sns-subscriptions";
import { Construct } from "constructs";

export interface OperationsProps {
  readonly stage: string;
  readonly alertEmail: string;
  readonly monthlyBudgetUsd: number;
}

/** The alert topic, the monthly budget, and the dashboard every function's alarm feeds. */
export class Operations extends Construct {
  readonly alertTopic: sns.Topic;
  readonly dashboard: cloudwatch.Dashboard;
  private readonly alarmAction: actions.SnsAction;

  constructor(scope: Construct, id: string, props: OperationsProps) {
    super(scope, id);
    this.alertTopic = new sns.Topic(this, "AlertTopic");
    this.alertTopic.addSubscription(new subscriptions.EmailSubscription(props.alertEmail));
    this.alarmAction = new actions.SnsAction(this.alertTopic);

    const alertAt = (threshold: number): budgets.CfnBudget.NotificationWithSubscribersProperty => ({
      notification: {
        notificationType: "ACTUAL",
        comparisonOperator: "GREATER_THAN",
        threshold,
        thresholdType: "PERCENTAGE",
      },
      subscribers: [{ subscriptionType: "EMAIL", address: props.alertEmail }],
    });
    new budgets.CfnBudget(this, "Budget", {
      budget: {
        budgetType: "COST",
        timeUnit: "MONTHLY",
        budgetLimit: { amount: props.monthlyBudgetUsd, unit: "USD" },
      },
      notificationsWithSubscribers: [alertAt(80), alertAt(100)],
    });

    this.dashboard = new cloudwatch.Dashboard(this, "Dashboard", {
      dashboardName: `ResearchArchive-${props.stage}`,
    });
  }

  /**
   * Alarm on API 5xx, and graph 4xx beside it. A REST API has no separate throttle metric, so
   * throttling (429) shows in the 4xx graph and does not alarm.
   */
  addApi(api: apigateway.RestApi): void {
    const period = Duration.minutes(5);
    const serverErrors = api.metricServerError({ statistic: "Sum", period });
    const alarm = serverErrors.createAlarm(api, "ServerErrorsAlarm", {
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    alarm.addAlarmAction(this.alarmAction);
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: "API",
        left: [api.metricClientError({ statistic: "Sum", period }), serverErrors],
        right: [api.metricCount({ statistic: "Sum", period })],
      }),
    );
  }

  /** Alarm on any error from the function, and graph its errors and duration. */
  addFunction(fn: lambda.Function): void {
    const errors = fn.metricErrors({ statistic: "Sum", period: Duration.minutes(5) });
    const alarm = errors.createAlarm(fn, "ErrorsAlarm", {
      threshold: 1,
      evaluationPeriods: 1,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    alarm.addAlarmAction(this.alarmAction);
    this.dashboard.addWidgets(
      new cloudwatch.GraphWidget({
        title: fn.node.path,
        left: [errors],
        right: [fn.metricDuration()],
      }),
    );
  }
}
