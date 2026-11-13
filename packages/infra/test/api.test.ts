import { Stack } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { expect, test } from "vitest";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

function archive(waf?: boolean): { template: Template } {
  const stack = new Stack(testApp(), "S");
  new ResearchArchive(stack, "Archive", {
    config: {
      publisher: "P",
      infrastructure: {
        alertEmail: "a@example.org",
        stages: [{ name: "prod" }],
        ...(waf === undefined ? {} : { modules: { waf } }),
      },
    },
    stage: "prod",
  });
  return { template: Template.fromStack(stack) };
}

function resourceId(template: Template, type: string, pathPart: string): string {
  const [id] = Object.entries(
    template.findResources(type, { Properties: { PathPart: pathPart } }),
  ).map(([key]) => key);
  if (!id) throw new Error(`no ${type} ${pathPart}`);
  return id;
}

test("health is public and whoami uses the Cognito authorizer", () => {
  const { template } = archive();
  const health = resourceId(template, "AWS::ApiGateway::Resource", "health");
  const whoami = resourceId(template, "AWS::ApiGateway::Resource", "whoami");
  const [authorizer] = Object.keys(template.findResources("AWS::ApiGateway::Authorizer"));

  template.hasResourceProperties("AWS::ApiGateway::Authorizer", { Type: "COGNITO_USER_POOLS" });
  template.hasResourceProperties("AWS::ApiGateway::Method", {
    HttpMethod: "GET",
    ResourceId: { Ref: health },
    AuthorizationType: "NONE",
  });
  template.hasResourceProperties("AWS::ApiGateway::Method", {
    HttpMethod: "GET",
    ResourceId: { Ref: whoami },
    AuthorizationType: "COGNITO_USER_POOLS",
    AuthorizerId: { Ref: authorizer },
  });
  template.hasResourceProperties("AWS::ApiGateway::RestApi", {
    EndpointConfiguration: { Types: ["REGIONAL"] },
  });
});

test("the stage throttles at 50 per second with a burst of 100", () => {
  archive().template.hasResourceProperties("AWS::ApiGateway::Stage", {
    MethodSettings: [
      Match.objectLike({
        HttpMethod: "*",
        ResourcePath: "/*",
        ThrottlingRateLimit: 50,
        ThrottlingBurstLimit: 100,
        MetricsEnabled: true,
      }),
    ],
  });
});

test("WAF appears only when modules.waf is true, associated with the API stage", () => {
  for (const off of [archive().template, archive(false).template]) {
    off.resourceCountIs("AWS::WAFv2::WebACL", 0);
    off.resourceCountIs("AWS::WAFv2::WebACLAssociation", 0);
  }

  const { template } = archive(true);
  const [stage] = Object.keys(template.findResources("AWS::ApiGateway::Stage"));
  const [acl] = Object.keys(template.findResources("AWS::WAFv2::WebACL"));
  const rules = template
    .toJSON()
    .Resources[acl!].Properties.Rules.map(
      (rule: { Statement: { ManagedRuleGroupStatement: { Name: string } } }) =>
        rule.Statement.ManagedRuleGroupStatement.Name,
    );
  template.hasResourceProperties("AWS::WAFv2::WebACL", {
    Scope: "REGIONAL",
    DefaultAction: { Allow: {} },
  });
  expect(rules).toEqual([
    "AWSManagedRulesCommonRuleSet",
    "AWSManagedRulesKnownBadInputsRuleSet",
    "AWSManagedRulesAmazonIpReputationList",
  ]);
  template.hasResourceProperties("AWS::WAFv2::WebACLAssociation", {
    WebACLArn: { "Fn::GetAtt": [acl, "Arn"] },
  });
  const association = Object.values(template.findResources("AWS::WAFv2::WebACLAssociation"))[0];
  expect(JSON.stringify(association?.Properties.ResourceArn)).toContain(stage);
});

test("the integrity check runs weekly with no retries", () => {
  const { template } = archive();
  const fns = template.findResources("AWS::Lambda::Function", {
    Properties: { Handler: "archive_backend.integrity.handler" },
  });
  const [fnId] = Object.keys(fns);

  expect(Object.values(fns)[0]?.Properties).toMatchObject({
    Timeout: 900,
    Environment: {
      Variables: { ARCHIVE_BUCKET: expect.anything(), ALERT_TOPIC_ARN: expect.anything() },
    },
  });
  template.hasResourceProperties("AWS::Scheduler::Schedule", {
    ScheduleExpression: "rate(7 days)",
    Target: {
      Arn: { "Fn::GetAtt": [fnId, "Arn"] },
      RetryPolicy: { MaximumRetryAttempts: 0 },
    },
  });
  template.hasResourceProperties("AWS::Lambda::EventInvokeConfig", {
    FunctionName: { Ref: fnId },
    MaximumRetryAttempts: 0,
  });
});

test("API 5xx alarms on the alert topic, and the dashboard graphs 4xx and 5xx", () => {
  const { template } = archive();
  const [restApi] = Object.keys(template.findResources("AWS::ApiGateway::RestApi"));
  const [topic] = Object.keys(template.findResources("AWS::SNS::Topic"));
  const apiName = template.toJSON().Resources[restApi!].Properties.Name;

  template.hasResourceProperties("AWS::CloudWatch::Alarm", {
    Namespace: "AWS/ApiGateway",
    MetricName: "5XXError",
    Dimensions: [{ Name: "ApiName", Value: apiName }],
    Statistic: "Sum",
    Period: 300,
    Threshold: 1,
    ComparisonOperator: "GreaterThanOrEqualToThreshold",
    TreatMissingData: "notBreaching",
    AlarmActions: [{ Ref: topic }],
  });
  template.resourcePropertiesCountIs(
    "AWS::CloudWatch::Alarm",
    { Namespace: "AWS/ApiGateway", MetricName: "4XXError" },
    0,
  );
  const body = JSON.stringify(
    Object.values(template.findResources("AWS::CloudWatch::Dashboard"))[0]?.Properties
      .DashboardBody,
  );
  expect(body).toContain("4XXError");
  expect(body).toContain("5XXError");
});
