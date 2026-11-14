import { CfnOutput, RemovalPolicy, Stack } from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import { Construct } from "constructs";
import { brandingAssets, brandingSettings, type LoginBrand } from "./brand";

export interface AuthProps {
  readonly stage: string;
  readonly isProd: boolean;
  /** The archive's brand: managed login's look and the invitation email's name. */
  readonly brand: LoginBrand;
}

/**
 * The user pool with email sign-in by invitation only, its role groups, and Cognito's managed
 * login in the archive's brand, offering a password or a passkey.
 */
export class Auth extends Construct {
  readonly userPool: cognito.UserPool;
  /** Managed login's base URL, which clients read from /auth-config.json. */
  readonly cognitoDomain: string;
  private readonly domain: cognito.UserPoolDomain;
  private readonly isProd: boolean;
  private readonly brand: LoginBrand;

  constructor(scope: Construct, id: string, props: AuthProps) {
    super(scope, id);
    this.isProd = props.isProd;
    this.brand = props.brand;
    const name = props.brand.name;
    // The email is HTML; the subject is plain text.
    const html = name.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    this.userPool = new cognito.UserPool(this, "UserPool", {
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      autoVerify: { email: true },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      // Choice-based sign-in: a password or a passkey. The passkey relying party is left to
      // Cognito's default, the prefix domain below (CloudFormation caps the ID at 63
      // characters, which the prefix domain's full name can pass).
      signInPolicy: { allowedFirstAuthFactors: { password: true, passkey: true } },
      passkeyUserVerification: cognito.PasskeyUserVerification.PREFERRED,
      // The site's address can't go in: the distribution depends on the API, whose
      // authorizer depends on this pool, so naming it here would be a cycle.
      userInvitation: {
        emailSubject: `Your ${name} account`,
        emailBody:
          `You've been invited to ${html}.<br><br>Sign in with your email address, {username}, ` +
          `and this temporary password: {####}<br><br>You'll choose your own password when ` +
          `you first sign in, and can add a passkey after.`,
      },
      ...(props.isProd
        ? { removalPolicy: RemovalPolicy.RETAIN, deletionProtection: true }
        : { removalPolicy: RemovalPolicy.DESTROY }),
    });
    for (const group of ["contributor", "curator", "admin"]) {
      new cognito.CfnUserPoolGroup(this, `${group}Group`, {
        userPoolId: this.userPool.userPoolId,
        groupName: group,
      });
    }
    this.domain = this.userPool.addDomain("Domain", {
      cognitoDomain: { domainPrefix: `archive-${props.stage}-${Stack.of(this).account}` },
      managedLoginVersion: cognito.ManagedLoginVersion.NEWER_MANAGED_LOGIN,
    });
    this.cognitoDomain = this.domain.baseUrl();
  }

  /**
   * The web app's and the CLI's clients: code with PKCE, no secret, each with managed login in
   * the archive's brand.
   */
  addAppClients(siteDomain: string): {
    web: cognito.UserPoolClient;
    cli: cognito.UserPoolClient;
  } {
    const client = (
      id: string,
      callbackUrls: string[],
      logoutUrls?: string[],
    ): cognito.UserPoolClient => {
      const appClient = this.userPool.addClient(id, {
        generateSecret: false,
        oAuth: {
          flows: { authorizationCodeGrant: true },
          scopes: [cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
          callbackUrls,
          logoutUrls,
        },
        // Choice-based sign-in (password or passkey) on managed login's page.
        authFlows: { user: true },
      });
      // Managed login shows no page for a client without branding.
      const branding = new cognito.CfnManagedLoginBranding(this, `${id}Branding`, {
        userPoolId: this.userPool.userPoolId,
        clientId: appClient.userPoolClientId,
        settings: brandingSettings(this.brand),
        assets: brandingAssets(this.brand),
      });
      branding.node.addDependency(this.domain);
      return appClient;
    };
    return {
      web: client("WebClient", [`https://${siteDomain}/auth/callback`], [`https://${siteDomain}/`]),
      cli: client("CliClient", ["http://localhost:8765/callback"]),
    };
  }

  /**
   * The test-only `e2e` client, for non-prod stages: admin password sign-in, so `just
   * ingest-e2e` signs in the throwaway users it creates. Its outputs are what the run reads.
   */
  addTestClient(): cognito.UserPoolClient {
    if (this.isProd) {
      throw new Error("the e2e client is never created on a prod stage");
    }
    const client = this.userPool.addClient("E2eClient", {
      userPoolClientName: "e2e",
      generateSecret: false,
      authFlows: { adminUserPassword: true },
      disableOAuth: true,
    });
    const stack = Stack.of(this);
    new CfnOutput(stack, "E2eClientId", { key: "E2eClientId", value: client.userPoolClientId });
    new CfnOutput(stack, "UserPoolId", { key: "UserPoolId", value: this.userPool.userPoolId });
    return client;
  }
}
