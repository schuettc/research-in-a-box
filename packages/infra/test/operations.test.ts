import { Stack } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import type { CfnFunction } from "aws-cdk-lib/aws-lambda";
import type { CfnTopic } from "aws-cdk-lib/aws-sns";
import { expect, test } from "vitest";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

function archive(stage = "prod"): { archive: ResearchArchive; stack: Stack } {
  const stack = new Stack(testApp(), "S");
  const built = new ResearchArchive(stack, "Archive", {
    config: {
      publisher: "P",
      infrastructure: {
        alertEmail: "a@example.org",
        monthlyBudgetUsd: 75,
        stages: [{ name: "prod" }, { name: "dev" }],
      },
    },
    stage,
  });
  return { archive: built, stack };
}

test("the alert topic emails the configured address", () => {
  const { archive: a, stack } = archive();
  const template = Template.fromStack(stack);

  template.hasResourceProperties("AWS::SNS::Subscription", {
    Protocol: "email",
    Endpoint: "a@example.org",
    TopicArn: { Ref: stack.getLogicalId(a.alertTopic.node.defaultChild as CfnTopic) },
  });
});

test("the budget is monthly, at the configured limit, and alerts at 80 and 100 percent", () => {
  const template = Template.fromStack(archive().stack);
  const notification = (threshold: number) => ({
    Notification: {
      NotificationType: "ACTUAL",
      ComparisonOperator: "GREATER_THAN",
      Threshold: threshold,
      ThresholdType: "PERCENTAGE",
    },
    Subscribers: [{ SubscriptionType: "EMAIL", Address: "a@example.org" }],
  });

  template.resourceCountIs("AWS::Budgets::Budget", 1);
  template.hasResourceProperties("AWS::Budgets::Budget", {
    Budget: {
      BudgetType: "COST",
      TimeUnit: "MONTHLY",
      BudgetLimit: { Amount: 75, Unit: "USD" },
    },
    NotificationsWithSubscribers: [notification(80), notification(100)],
  });
});

test("pythonFunction makes an arm64 Python 3.13 function with an errors alarm on the alert topic", () => {
  const { archive: a, stack } = archive();
  const fn = a.pythonFunction("Probe", { handler: "archive_backend.health.handler" });
  const template = Template.fromStack(stack);
  const fnId = stack.getLogicalId(fn.node.defaultChild as CfnFunction);

  expect(template.toJSON().Resources[fnId].Properties).toMatchObject({
    Runtime: "python3.13",
    Architectures: ["arm64"],
    Handler: "archive_backend.health.handler",
    Timeout: 30,
    MemorySize: 512,
  });
  template.hasResourceProperties("AWS::CloudWatch::Alarm", {
    MetricName: "Errors",
    Namespace: "AWS/Lambda",
    Dimensions: [{ Name: "FunctionName", Value: { Ref: fnId } }],
    Statistic: "Sum",
    Period: 300,
    EvaluationPeriods: 1,
    Threshold: 1,
    ComparisonOperator: "GreaterThanOrEqualToThreshold",
    TreatMissingData: "notBreaching",
    AlarmActions: [{ Ref: stack.getLogicalId(a.alertTopic.node.defaultChild as CfnTopic) }],
  });
  template.hasResourceProperties("AWS::Logs::LogGroup", { RetentionInDays: 30 });
});

test("there is one dashboard per stage", () => {
  for (const stage of ["prod", "dev"]) {
    const template = Template.fromStack(archive(stage).stack);
    template.resourceCountIs("AWS::CloudWatch::Dashboard", 1);
    template.hasResourceProperties("AWS::CloudWatch::Dashboard", {
      DashboardName: `ResearchArchive-${stage}`,
      DashboardBody: Match.anyValue(),
    });
  }
});
