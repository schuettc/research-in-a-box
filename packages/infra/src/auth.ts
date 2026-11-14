import { RemovalPolicy, Stack } from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import { Construct } from "constructs";

export interface AuthProps {
  readonly stage: string;
  readonly isProd: boolean;
}

/** The user pool with email sign-in by invitation only, its role groups, and Cognito's managed login. */
export class Auth extends Construct {
  readonly userPool: cognito.UserPool;
  private readonly domain: cognito.UserPoolDomain;

  constructor(scope: Construct, id: string, props: AuthProps) {
    super(scope, id);
    this.userPool = new cognito.UserPool(this, "UserPool", {
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      autoVerify: { email: true },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
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
  }

  /** The web app's and the CLI's clients: code with PKCE, no secret, each with managed login. */
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
      });
      // Managed login shows no page for a client without branding.
      const branding = new cognito.CfnManagedLoginBranding(this, `${id}Branding`, {
        userPoolId: this.userPool.userPoolId,
        clientId: appClient.userPoolClientId,
        useCognitoProvidedValues: true,
      });
      branding.node.addDependency(this.domain);
      return appClient;
    };
    return {
      web: client("WebClient", [`https://${siteDomain}/auth/callback`], [`https://${siteDomain}/`]),
      cli: client("CliClient", ["http://localhost:8765/callback"]),
    };
  }
}
