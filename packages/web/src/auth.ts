import { InMemoryWebStorage, User, UserManager, WebStorageStateStore } from "oidc-client-ts";

/** The fields the web app reads from the `/auth-config.json` the stage's deploy writes. */
interface AuthConfig {
  region: string;
  cognitoDomain: string;
  webClientId: string;
}

/** The signed-in user lives in memory only, and its refresh token is dropped before it is kept. */
class MemoryUserStore extends WebStorageStateStore {
  constructor() {
    super({ store: new InMemoryWebStorage() });
  }

  override set(key: string, value: string): Promise<void> {
    const user = JSON.parse(value) as Record<string, unknown>;
    delete user.refresh_token;
    return super.set(key, JSON.stringify(user));
  }
}

let manager: Promise<UserManager> | null = null;
let user: User | null = null;
let callback: Promise<string> | null = null;

async function createManager(): Promise<UserManager> {
  const response = await fetch("/auth-config.json");
  if (!response.ok) throw new Error(`/auth-config.json answered ${response.status}`);
  const config = (await response.json()) as AuthConfig;
  const domain = config.cognitoDomain.replace(/\/$/, "");
  return new UserManager({
    // Cognito's managed login, named directly so no discovery request is needed.
    authority: domain,
    metadata: {
      issuer: domain,
      authorization_endpoint: `${domain}/oauth2/authorize`,
      token_endpoint: `${domain}/oauth2/token`,
      end_session_endpoint: `${domain}/logout`,
    },
    client_id: config.webClientId,
    redirect_uri: `${location.origin}/auth/callback`,
    response_type: "code",
    scope: "openid email profile",
    userStore: new MemoryUserStore(),
    // Only the PKCE state and the page to return to cross the redirect.
    stateStore: new WebStorageStateStore({ store: sessionStorage }),
    automaticSilentRenew: false,
  });
}

function userManager(): Promise<UserManager> {
  manager ??= createManager().catch((error: unknown) => {
    manager = null;
    throw error;
  });
  return manager;
}

/** Go to managed login, coming back to `returnTo` once signed in. */
export async function signIn(returnTo: string): Promise<void> {
  await (await userManager()).signinRedirect({ state: returnTo });
}

/**
 * Finish sign-in from the callback URL and answer the page to return to. Run once even when
 * the callback page renders twice, since its state is used up.
 */
export function completeSignIn(url: string = location.href): Promise<string> {
  callback ??= (async () => {
    const signedIn = await (await userManager()).signinRedirectCallback(url);
    signedIn.refresh_token = undefined;
    user = signedIn;
    return typeof signedIn.state === "string" ? signedIn.state : "/";
  })();
  return callback;
}

/** The access token while the reader is signed in, else null. */
export function accessToken(): string | null {
  if (!user || user.expired) return null;
  return user.access_token;
}
