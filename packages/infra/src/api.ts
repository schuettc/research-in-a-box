import * as apigateway from "aws-cdk-lib/aws-apigateway";
import type * as cognito from "aws-cdk-lib/aws-cognito";
import type * as lambda from "aws-cdk-lib/aws-lambda";
import * as wafv2 from "aws-cdk-lib/aws-wafv2";
import { Construct } from "constructs";

export interface ApiProps {
  readonly userPool: cognito.IUserPool;
  readonly waf: boolean;
  readonly health: lambda.IFunction;
  readonly whoami: lambda.IFunction;
}

const MANAGED_RULE_GROUPS = [
  "AWSManagedRulesCommonRuleSet",
  "AWSManagedRulesKnownBadInputsRuleSet",
  "AWSManagedRulesAmazonIpReputationList",
];

/**
 * The REST API under `/api`, with fixed stage throttling and a Cognito authorizer. `whoami`
 * exists because CDK refuses an authorizer attached to no method, and it proves a signed-in call.
 */
export class Api extends Construct {
  readonly restApi: apigateway.RestApi;
  readonly authorizer: apigateway.CognitoUserPoolsAuthorizer;

  constructor(scope: Construct, id: string, props: ApiProps) {
    super(scope, id);
    this.restApi = new apigateway.RestApi(this, "RestApi", {
      endpointConfiguration: { types: [apigateway.EndpointType.REGIONAL] },
      deployOptions: {
        throttlingRateLimit: 50,
        throttlingBurstLimit: 100,
        metricsEnabled: true,
      },
    });
    this.authorizer = new apigateway.CognitoUserPoolsAuthorizer(this, "Authorizer", {
      cognitoUserPools: [props.userPool],
    });

    const api = this.restApi.root.addResource("api");
    api.addResource("health").addMethod("GET", new apigateway.LambdaIntegration(props.health), {
      authorizationType: apigateway.AuthorizationType.NONE,
    });
    api.addResource("whoami").addMethod("GET", new apigateway.LambdaIntegration(props.whoami), {
      authorizationType: apigateway.AuthorizationType.COGNITO,
      authorizer: this.authorizer,
    });

    if (props.waf) {
      const acl = new wafv2.CfnWebACL(this, "WebAcl", {
        scope: "REGIONAL",
        defaultAction: { allow: {} },
        visibilityConfig: {
          cloudWatchMetricsEnabled: true,
          metricName: "ArchiveApi",
          sampledRequestsEnabled: true,
        },
        rules: MANAGED_RULE_GROUPS.map((name, priority) => ({
          name,
          priority,
          overrideAction: { none: {} },
          statement: { managedRuleGroupStatement: { vendorName: "AWS", name } },
          visibilityConfig: {
            cloudWatchMetricsEnabled: true,
            metricName: name,
            sampledRequestsEnabled: true,
          },
        })),
      });
      new wafv2.CfnWebACLAssociation(this, "WebAclAssociation", {
        webAclArn: acl.attrArn,
        resourceArn: this.restApi.deploymentStage.stageArn,
      });
    }
  }
}
