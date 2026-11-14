import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";

const DOMAIN = "https://archive-test-123.auth.us-east-1.amazoncognito.com";
const CONFIG = {
  region: "us-east-1",
  cognitoDomain: DOMAIN,
  webClientId: "web-client-id",
  cliClientId: "cli-client-id",
};
const ACCESS_TOKEN = "eyJhbGciOiJSUzI1NiJ9.access-token-body.signature";
const REFRESH_TOKEN = "refresh-token-value";

function jwt(claims: object): string {
  const part = (value: object) => btoa(JSON.stringify(value)).replace(/=+$/, "");
  return `${part({ alg: "RS256" })}.${part(claims)}.signature`;
}
const now = Math.floor(Date.now() / 1000);
const ID_TOKEN = jwt({
  sub: "reader-1",
  aud: "web-client-id",
  iss: DOMAIN,
  iat: now,
  exp: now + 3600,
});

let fetchMock: Mock;
let assign: Mock;

beforeEach(() => {
  vi.resetModules();
  sessionStorage.clear();
  localStorage.clear();
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/auth-config.json") return Response.json(CONFIG);
    if (url === `${DOMAIN}/oauth2/token` && init?.method === "POST") {
      return Response.json({
        access_token: ACCESS_TOKEN,
        id_token: ID_TOKEN,
        refresh_token: REFRESH_TOKEN,
        token_type: "Bearer",
        expires_in: 3600,
      });
    }
    if (url.startsWith("/api/datasets/ds-1/versions/2/download")) {
      return Response.json({ url: "https://bucket.example/restricted/ds-1/2/a.csv?sig" });
    }
    return Response.json({}, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  // oidc-client-ts navigates with window.self.location.assign; jsdom can't navigate.
  assign = vi.fn();
  vi.spyOn(window, "self", "get").mockReturnValue({
    location: { assign },
  } as unknown as Window & typeof globalThis);
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function redirectUrl(): Promise<URL> {
  const { signIn } = await import("./auth");
  void signIn("/datasets/ds-1");
  await vi.waitFor(() => expect(assign).toHaveBeenCalled());
  return new URL(String(assign.mock.calls[0]?.[0]));
}

test("the sign-in redirect carries the client id, a PKCE challenge and the callback URL", async () => {
  const url = await redirectUrl();

  expect(`${url.origin}${url.pathname}`).toBe(`${DOMAIN}/oauth2/authorize`);
  expect(url.searchParams.get("client_id")).toBe("web-client-id");
  expect(url.searchParams.get("redirect_uri")).toBe(`${location.origin}/auth/callback`);
  expect(url.searchParams.get("response_type")).toBe("code");
  expect(url.searchParams.get("code_challenge")).toMatch(/^[\w-]{43}$/);
  expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  expect(url.searchParams.get("scope")).not.toContain("offline_access");
});

test("after the callback, the download request carries the bearer token", async () => {
  const state = (await redirectUrl()).searchParams.get("state");
  const { accessToken, completeSignIn } = await import("./auth");
  const { downloadLink } = await import("./api");

  const returnTo = await completeSignIn(`${location.origin}/auth/callback?code=abc&state=${state}`);
  const link = await downloadLink("ds-1", 2, "data/a.csv", accessToken() ?? "");

  expect(returnTo).toBe("/datasets/ds-1");
  expect(link).toBe("https://bucket.example/restricted/ds-1/2/a.csv?sig");
  const [url, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  expect(url).toBe("/api/datasets/ds-1/versions/2/download?path=data%2Fa.csv");
  expect(new Headers(init.headers).get("Authorization")).toBe(`Bearer ${ACCESS_TOKEN}`);
});

test("nothing token-shaped is written to localStorage or sessionStorage", async () => {
  const state = (await redirectUrl()).searchParams.get("state");
  const { completeSignIn } = await import("./auth");
  await completeSignIn(`${location.origin}/auth/callback?code=abc&state=${state}`);

  for (const storage of [localStorage, sessionStorage]) {
    const stored = Object.keys(storage)
      .map((key) => `${key}=${storage.getItem(key)}`)
      .join("\n");
    expect(stored).not.toContain(ACCESS_TOKEN);
    expect(stored).not.toContain(ID_TOKEN);
    expect(stored).not.toContain(REFRESH_TOKEN);
    expect(stored).not.toMatch(/eyJ[\w-]+\.[\w-]+\./);
  }
});

test("the user is kept in memory without its refresh token", async () => {
  const { InMemoryWebStorage } = await import("oidc-client-ts");
  const setItem = vi.spyOn(InMemoryWebStorage.prototype, "setItem");
  const state = (await redirectUrl()).searchParams.get("state");
  const auth = await import("./auth");
  await auth.completeSignIn(`${location.origin}/auth/callback?code=abc&state=${state}`);

  expect(auth.accessToken()).toBe(ACCESS_TOKEN);
  const stored = setItem.mock.calls.map(([, value]) => value).join("\n");
  expect(stored).toContain(ACCESS_TOKEN);
  expect(stored).not.toContain(REFRESH_TOKEN);
});
