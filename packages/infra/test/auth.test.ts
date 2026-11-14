import { fileURLToPath } from "node:url";
import { Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { expect, test } from "vitest";
import { createApp } from "../bin/app";
import { Auth } from "../src/auth";
import { loginBrand } from "../src/brand";
import { ResearchArchive } from "../src/research-archive";
import { testApp } from "./test-app";

const REPO = fileURLToPath(new URL("../../../", import.meta.url));
const BRAND = loginBrand(
  {
    publisher: "Invented Research Cooperative",
    brand: {
      name: "Lake Archive",
      primaryColor: "#0b5cad",
      logo: "examples/brand/logo.svg",
      favicon: "examples/brand/favicon.svg",
    },
  },
  REPO,
);

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
  const auth = new Auth(stack, "Auth", { stage: "dev", isProd: false, brand: BRAND });
  auth.addAppClients("d123.cloudfront.net");
  return Template.fromStack(stack);
}

test("the user pool signs in with email, takes invited users only, and has contributor, curator and admin groups", () => {
  const template = archive();

  template.resourceCountIs("AWS::Cognito::UserPool", 1);
  template.hasResourceProperties("AWS::Cognito::UserPool", {
    UsernameAttributes: ["email"],
    AutoVerifiedAttributes: ["email"],
    AdminCreateUserConfig: { AllowAdminCreateUserOnly: true },
    AccountRecoverySetting: {
      RecoveryMechanisms: [{ Name: "verified_email", Priority: 1 }],
    },
  });
  const groups = Object.values(template.findResources("AWS::Cognito::UserPoolGroup")).map(
    (group) => group.Properties.GroupName,
  );
  expect(groups.sort()).toEqual(["admin", "contributor", "curator"]);
});

test("managed login is the newer version, and each client has the archive's branding", () => {
  const template = authWithClients();

  template.hasResourceProperties("AWS::Cognito::UserPoolDomain", {
    ManagedLoginVersion: 2,
    Domain: { "Fn::Join": ["", ["archive-dev-", { Ref: "AWS::AccountId" }]] },
  });
  const clients = Object.keys(template.findResources("AWS::Cognito::UserPoolClient"));
  expect(clients).toHaveLength(2);
  const branded = Object.values(template.findResources("AWS::Cognito::ManagedLoginBranding")).map(
    (branding) => {
      expect(branding.Properties.UseCognitoProvidedValues).toBeUndefined();
      const button = branding.Properties.Settings.components.primaryButton.lightMode.defaults;
      expect(button.backgroundColor).toBe("0b5cadff");
      const categories = branding.Properties.Assets.map((a: { Category: string }) => a.Category);
      expect(categories).toEqual(["FORM_LOGO", "FAVICON_SVG"]);
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

test("the pool offers password and passkey sign-in, preferring user verification", () => {
  const template = authWithClients();

  template.hasResourceProperties("AWS::Cognito::UserPool", {
    Policies: { SignInPolicy: { AllowedFirstAuthFactors: ["PASSWORD", "WEB_AUTHN"] } },
    WebAuthnUserVerification: "preferred",
  });
  // The relying party is left to Cognito's default, the prefix domain: CloudFormation caps the
  // ID at 63 characters, which archive-<stage>-<account>.auth.<region>.amazoncognito.com passes.
  const [pool] = Object.values(template.findResources("AWS::Cognito::UserPool"));
  expect(pool?.Properties.WebAuthnRelyingPartyID).toBeUndefined();
  template.hasResourceProperties("AWS::Cognito::UserPoolDomain", {
    Domain: { "Fn::Join": ["", ["archive-dev-", { Ref: "AWS::AccountId" }]] },
  });
});

test("both app clients allow choice-based sign-in alongside the code flow", () => {
  const template = authWithClients();

  const clients = Object.values(template.findResources("AWS::Cognito::UserPoolClient"));
  expect(clients).toHaveLength(2);
  for (const client of clients) {
    expect(client.Properties.ExplicitAuthFlows).toContain("ALLOW_USER_AUTH");
    expect(client.Properties.AllowedOAuthFlows).toEqual(["code"]);
  }
});

test("the invitation email speaks in the archive's name", () => {
  const template = authWithClients();

  const [pool] = Object.values(template.findResources("AWS::Cognito::UserPool"));
  const invite = pool?.Properties.AdminCreateUserConfig.InviteMessageTemplate;
  expect(invite.EmailSubject).toBe("Your Lake Archive account");
  expect(invite.EmailMessage).toContain("Lake Archive");
  expect(invite.EmailMessage).toContain("{username}");
  expect(invite.EmailMessage).toContain("{####}");
});

test("a non-prod stage has the e2e client, with admin password sign-in and no secret, and its outputs", () => {
  const template = archive("dev");

  template.resourceCountIs("AWS::Cognito::UserPoolClient", 3);
  template.hasResourceProperties("AWS::Cognito::UserPoolClient", {
    ClientName: "e2e",
    ExplicitAuthFlows: ["ALLOW_ADMIN_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
    GenerateSecret: false,
    AllowedOAuthFlowsUserPoolClient: false,
  });
  const outputs = Object.keys(template.findOutputs("*"));
  expect(outputs).toEqual(expect.arrayContaining(["E2eClientId", "UserPoolId", "SiteDomain"]));
});

test("a prod stage has no e2e client, no admin password sign-in on any client, and no e2e outputs", () => {
  const template = archive("prod");

  const clients = Object.values(template.findResources("AWS::Cognito::UserPoolClient"));
  expect(clients).toHaveLength(2);
  for (const client of clients) {
    expect(client.Properties.ClientName).not.toBe("e2e");
    expect(JSON.stringify(client.Properties.ExplicitAuthFlows ?? [])).not.toContain(
      "ADMIN_USER_PASSWORD_AUTH",
    );
  }
  const outputs = Object.keys(template.findOutputs("*"));
  expect(outputs).not.toContain("E2eClientId");
  expect(outputs).not.toContain("UserPoolId");
});

test("the ingest-test config makes only the ingest-test stack, with the e2e client", () => {
  const config = fileURLToPath(
    new URL("../../../examples/ingest-test-stage/archive.yaml", import.meta.url),
  );
  const app = createApp(config);

  const stacks = app.node.children.filter((child): child is Stack => child instanceof Stack);
  expect(stacks.map((stack) => stack.stackName)).toEqual(["ResearchArchive-ingest-test"]);
  const [stack] = stacks;
  Template.fromStack(stack as Stack).hasResourceProperties("AWS::Cognito::UserPoolClient", {
    ClientName: "e2e",
  });
});

test("the e2e client refuses a prod pool", () => {
  const auth = new Auth(new Stack(testApp(), "S"), "Auth", {
    stage: "prod",
    isProd: true,
    brand: BRAND,
  });

  expect(() => auth.addTestClient()).toThrow(/prod/);
});

test("the prod user pool is retained with deletion protection; a dev stage's is not", () => {
  const [prod] = Object.values(archive("prod").findResources("AWS::Cognito::UserPool"));
  const [dev] = Object.values(archive("dev").findResources("AWS::Cognito::UserPool"));

  expect(prod?.DeletionPolicy).toBe("Retain");
  expect(prod?.Properties.DeletionProtection).toBe("ACTIVE");
  expect(dev?.DeletionPolicy).toBe("Delete");
  expect(dev?.Properties.DeletionProtection).not.toBe("ACTIVE");
});

test("the app's archive.yaml brands managed login with its colour and logo", () => {
  const app = createApp(fileURLToPath(new URL("../../../archive.yaml", import.meta.url)));

  const [stack] = app.node.children.filter((child): child is Stack => child instanceof Stack);
  const brandings = Template.fromStack(stack as Stack).findResources(
    "AWS::Cognito::ManagedLoginBranding",
  );
  for (const branding of Object.values(brandings)) {
    const button = branding.Properties.Settings.components.primaryButton.lightMode.defaults;
    expect(button.backgroundColor).toBe("24395fff");
    expect(branding.Properties.Assets[0].Category).toBe("FORM_LOGO");
  }
});
