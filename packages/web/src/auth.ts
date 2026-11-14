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

const RETURN_TO_KEY = "sign-in-return-to";
// Set while the reader is away adding a passkey: the page to offer when they come back.
const PASSKEY_KEY = "passkey-add-return-to";

let manager: Promise<UserManager> | null = null;
let user: User | null = null;
let callback: Promise<string> | null = null;
const listeners = new Set<() => void>();

function changed(): void {
  for (const listener of listeners) listener();
}

/** Hear when the reader signs in or out; answers the function that stops listening. */
export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

async function readConfig(): Promise<AuthConfig & { domain: string }> {
  const response = await fetch("/auth-config.json");
  if (!response.ok) throw new Error(`/auth-config.json answered ${response.status}`);
  const config = (await response.json()) as AuthConfig;
  return { ...config, domain: config.cognitoDomain.replace(/\/$/, "") };
}

async function createManager(): Promise<UserManager> {
  const config = await readConfig();
  const domain = config.domain;
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
  sessionStorage.setItem(RETURN_TO_KEY, returnTo);
  await (await userManager()).signinRedirect({ state: returnTo });
}

/** The page the last sign-in set out from, so a failed one can offer the way back. */
export function lastReturnTo(): string {
  return sessionStorage.getItem(RETURN_TO_KEY) ?? "/";
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
    changed();
    return typeof signedIn.state === "string" ? signedIn.state : "/";
  })();
  return callback;
}

/**
 * The token the API accepts while the reader is signed in, else null: the ID token, since the
 * API's Cognito authorizer has no OAuth scopes and so checks ID tokens, not access tokens.
 */
export function apiToken(): string | null {
  if (!user || user.expired) return null;
  return user.id_token ?? null;
}

/** The signed-in reader's email, or null. */
export function signedInEmail(): string | null {
  if (!user || user.expired) return null;
  const email = user.profile.email;
  return typeof email === "string" ? email : null;
}

// Navigate as oidc-client-ts does, through window.self, so tests can watch it.
const go = (url: string) => window.self.location.assign(url);

/** Forget the reader here, then end the managed login session and come back to the site root. */
export async function signOut(): Promise<void> {
  user = null;
  callback = null;
  changed();
  const config = await readConfig();
  const query = new URLSearchParams({
    client_id: config.webClientId,
    logout_uri: `${location.origin}/`,
  });
  go(`${config.domain}/logout?${query}`);
}

/**
 * Managed login's page for adding a passkey. It comes back to the sign-in callback without a
 * code, so the page to return to is kept for the callback to tell the two apart.
 */
export async function addPasskey(returnTo: string): Promise<void> {
  sessionStorage.setItem(PASSKEY_KEY, returnTo);
  const config = await readConfig();
  const query = new URLSearchParams({
    client_id: config.webClientId,
    redirect_uri: `${location.origin}/auth/callback`,
  });
  go(`${config.domain}/passkeys/add?${query}`);
}

/**
 * The page to return to when the callback is managed login coming back from adding a passkey
 * (the callback's `search` has no code and a passkey was being added), else null.
 */
export function passkeyReturn(search: string): string | null {
  if (new URLSearchParams(search).has("code")) return null;
  return sessionStorage.getItem(PASSKEY_KEY);
}

/** Forget that a passkey was being added, once the callback has shown it. */
export function clearPasskeyReturn(): void {
  sessionStorage.removeItem(PASSKEY_KEY);
}
