import { CfnOutput, Stack } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import { Construct } from "constructs";

const GITHUB_ISSUER = "token.actions.githubusercontent.com";
const STS_AUDIENCE = "sts.amazonaws.com";
const BOOTSTRAP_ROLES = ["deploy", "file-publishing", "image-publishing", "lookup"];

export interface DeployAccessProps {
  /** The fork, `owner/name`. */
  readonly githubRepo: string;
  /** The stages whose GitHub environments may deploy into this account. */
  readonly stages: string[];
}

/**
 * GitHub's OIDC provider and the one role GitHub Actions assumes to deploy. The role trusts only
 * the repo's environments for the given stages, and may only assume the CDK bootstrap roles, the
 * way CDK itself scopes a deploy.
 */
export class DeployAccess extends Construct {
  readonly role: iam.Role;

  constructor(scope: Construct, id: string, props: DeployAccessProps) {
    super(scope, id);
    const account = Stack.of(this).account;

    const provider = new iam.OidcProviderNative(this, "GitHubOidc", {
      url: `https://${GITHUB_ISSUER}`,
      clientIds: [STS_AUDIENCE],
    });

    this.role = new iam.Role(this, "Role", {
      description: `GitHub Actions deploys of ${props.githubRepo}`,
      assumedBy: new iam.WebIdentityPrincipal(provider.oidcProviderArn, {
        StringEquals: {
          [`${GITHUB_ISSUER}:aud`]: STS_AUDIENCE,
          [`${GITHUB_ISSUER}:sub`]: props.stages.map(
            (stage) => `repo:${props.githubRepo}:environment:${stage}`,
          ),
        },
      }),
    });
    this.role.addToPolicy(
      new iam.PolicyStatement({
        actions: ["sts:AssumeRole"],
        resources: BOOTSTRAP_ROLES.map(
          (kind) => `arn:aws:iam::${account}:role/cdk-*-${kind}-role-${account}-*`,
        ),
      }),
    );

    new CfnOutput(Stack.of(this), "DeployRoleArn", {
      key: "DeployRoleArn",
      value: this.role.roleArn,
    });
  }
}
