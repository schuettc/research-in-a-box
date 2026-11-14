import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Template } from "aws-cdk-lib/assertions";
import { expect, test } from "vitest";
import { createDeployAccessApp, DEPLOY_STACK_NAME } from "../bin/deploy-access";

function configFile(yaml: string): string {
  const path = join(mkdtempSync(join(tmpdir(), "archive-config-")), "archive.yaml");
  writeFileSync(path, yaml, "utf-8");
  return path;
}

const ACCOUNT = "123456789012";
const TWO_STAGES = configFile(
  "publisher: P\ninfrastructure:\n  alertEmail: a@example.org\n  stages:\n" +
    "    - name: dev\n" +
    `    - name: prod\n      account: '${ACCOUNT}'\n` +
    "    - name: elsewhere\n      account: '210987654321'\n",
);

type Statement = {
  Effect: string;
  Action: string | string[];
  Resource?: unknown;
  Condition?: Record<string, Record<string, unknown>>;
  Principal?: Record<string, unknown>;
};

function synth(configPath: string, context: Record<string, string>): Template {
  const app = createDeployAccessApp(configPath, context, { account: ACCOUNT, region: "us-east-1" });
  return Template.fromStack(app.node.findChild(DEPLOY_STACK_NAME) as never);
}

function role(template: Template): {
  trust: Statement[];
  policies: Statement[];
} {
  const roles = template.findResources("AWS::IAM::Role");
  expect(Object.keys(roles)).toHaveLength(1);
  const props = Object.values(roles)[0]!.Properties as {
    AssumeRolePolicyDocument: { Statement: Statement[] };
  };
  const policies = Object.values(template.findResources("AWS::IAM::Policy")).flatMap(
    (p) =>
      (p.Properties as { PolicyDocument: { Statement: Statement[] } }).PolicyDocument.Statement,
  );
  return { trust: props.AssumeRolePolicyDocument.Statement, policies };
}

test("the OIDC provider is GitHub's, for STS", () => {
  const template = synth(TWO_STAGES, { githubRepo: "owner/fork" });

  template.resourceCountIs("AWS::IAM::OIDCProvider", 1);
  template.hasResourceProperties("AWS::IAM::OIDCProvider", {
    Url: "https://token.actions.githubusercontent.com",
    ClientIdList: ["sts.amazonaws.com"],
  });
});

test("the role trusts exactly the repo's environments for the stages in this account", () => {
  const { trust } = role(synth(TWO_STAGES, { githubRepo: "owner/fork" }));

  expect(trust).toHaveLength(1);
  expect(trust[0]!.Action).toBe("sts:AssumeRoleWithWebIdentity");
  expect(trust[0]!.Condition).toEqual({
    StringEquals: {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub": [
        "repo:owner/fork:environment:dev",
        "repo:owner/fork:environment:prod",
      ],
    },
  });
  expect(JSON.stringify(trust)).not.toContain("StringLike");
});

test("the role may only assume the CDK bootstrap roles in its account", () => {
  const { policies } = role(synth(TWO_STAGES, { githubRepo: "owner/fork" }));

  expect(policies).toEqual([
    {
      Effect: "Allow",
      Action: "sts:AssumeRole",
      Resource: ["deploy", "file-publishing", "image-publishing", "lookup"].map(
        (kind) => `arn:aws:iam::${ACCOUNT}:role/cdk-*-${kind}-role-${ACCOUNT}-*`,
      ),
    },
  ]);
});

test("the stack outputs the role's ARN and carries the Repo tag", () => {
  const app = createDeployAccessApp(
    TWO_STAGES,
    { githubRepo: "owner/fork" },
    { account: ACCOUNT, region: "us-east-1" },
  );
  const template = Template.fromStack(app.node.findChild(DEPLOY_STACK_NAME) as never);
  const stack = app.synth().getStackByName(DEPLOY_STACK_NAME);

  expect(Object.keys(template.findOutputs("DeployRoleArn"))).toEqual(["DeployRoleArn"]);
  expect(stack.tags).toEqual({ Repo: "schuettc/research-in-a-box" });
});

test("synth fails with a clear message without githubRepo", () => {
  expect(() => synth(TWO_STAGES, {})).toThrow(
    /githubRepo is required: run with -c githubRepo=<owner>\/<name>/,
  );
});

test("a githubRepo that isn't owner/name is refused", () => {
  expect(() => synth(TWO_STAGES, { githubRepo: "owner/*" })).toThrow(/githubRepo/);
});
