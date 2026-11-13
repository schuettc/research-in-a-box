import { Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { expect, test } from "vitest";
import { Auth } from "../src/auth";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

function archive(stage = "prod"): Template {
  const stack = new Stack(testApp(), "S");
  new ResearchArchive(stack, "Archive", {
    config: {
      publisher: "P",
      infrastructure: { alertEmail: "a@example.org", stages: [{ name: "prod" }, { name: "dev" }] },
    },
    stage,
  });
  return Template.fromStack(stack);
}

function authWithClients(): Template {
  const stack = new Stack(testApp(), "S");
  const auth = new Auth(stack, "Auth", { stage: "dev", isProd: false });
  auth.addAppClients("d123.cloudfront.net");
  return Template.fromStack(stack);
}

test("the user pool signs in with email and has contributor, curator and admin groups", () => {
  const template = archive();

  template.resourceCountIs("AWS::Cognito::UserPool", 1);
  template.hasResourceProperties("AWS::Cognito::UserPool", {
    UsernameAttributes: ["email"],
    AutoVerifiedAttributes: ["email"],
    AdminCreateUserConfig: { AllowAdminCreateUserOnly: false },
    AccountRecoverySetting: {
      RecoveryMechanisms: [{ Name: "verified_email", Priority: 1 }],
    },
  });
  const groups = Object.values(template.findResources("AWS::Cognito::UserPoolGroup")).map(
    (group) => group.Properties.GroupName,
  );
  expect(groups.sort()).toEqual(["admin", "contributor", "curator"]);
});

test("managed login is the newer version, and each client has branding", () => {
  const template = authWithClients();

  template.hasResourceProperties("AWS::Cognito::UserPoolDomain", {
    ManagedLoginVersion: 2,
    Domain: { "Fn::Join": ["", ["archive-dev-", { Ref: "AWS::AccountId" }]] },
  });
  const clients = Object.keys(template.findResources("AWS::Cognito::UserPoolClient"));
  expect(clients).toHaveLength(2);
  const branded = Object.values(template.findResources("AWS::Cognito::ManagedLoginBranding")).map(
    (branding) => {
      expect(branding.Properties.UseCognitoProvidedValues).toBe(true);
      return branding.Properties.ClientId.Ref as string;
    },
  );
  expect(branded.sort()).toEqual(clients.sort());
});

test("both app clients use code with PKCE and no secret, with the site and localhost callbacks", () => {
  const template = authWithClients();
  const common = {
    AllowedOAuthFlows: ["code"],
    AllowedOAuthFlowsUserPoolClient: true,
    AllowedOAuthScopes: ["openid", "email", "profile"],
    GenerateSecret: false,
  };

  template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
    ...common,
    CallbackURLs: ["https://d123.cloudfront.net/auth/callback"],
    LogoutURLs: ["https://d123.cloudfront.net/"],
  });
  template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
    ...common,
    CallbackURLs: ["http://localhost:8765/callback"],
  });
});

test("the prod user pool is retained with deletion protection; a dev stage's is not", () => {
  const [prod] = Object.values(archive("prod").findResources("AWS::Cognito::UserPool"));
  const [dev] = Object.values(archive("dev").findResources("AWS::Cognito::UserPool"));

  expect(prod?.DeletionPolicy).toBe("Retain");
  expect(prod?.Properties.DeletionProtection).toBe("ACTIVE");
  expect(dev?.DeletionPolicy).toBe("Delete");
  expect(dev?.Properties.DeletionProtection).not.toBe("ACTIVE");
});
