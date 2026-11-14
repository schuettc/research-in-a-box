import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter, useNavigate } from "react-router";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AppRoutes } from "./App";
import { addPasskey, completeSignIn, signIn, signOut, signedInEmail } from "./auth";

vi.mock("./auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./auth")>()),
  signedInEmail: vi.fn(() => null),
  signOut: vi.fn(async () => {}),
  addPasskey: vi.fn(async () => {}),
  signIn: vi.fn(async () => {}),
  completeSignIn: vi.fn(() => new Promise(() => {})),
}));

const MANIFEST = { id: "ds-1", title: "Lake levels", "archive:access": "open" };
const NAME = "Invented Research Cooperative";

/** The dataset routes get a dataset; search waits forever, since its heading needs no answer. */
async function answer(url: string): Promise<Response> {
  const path = new URL(url, "https://site").pathname;
  if (path === "/api/datasets/ds-1") {
    return Response.json({
      id: "ds-1",
      title: "Lake levels",
      access: "open",
      currentVersion: 2,
      prefix: "open/ds-1/2/",
      manifest: MANIFEST,
      files: [],
    });
  }
  if (path === "/api/datasets/ds-1/versions/2") {
    return Response.json({ version: 2, prefix: "open/ds-1/2/", manifest: MANIFEST, files: [] });
  }
  if (path === "/api/datasets/ds-1/versions") {
    return Response.json({ versions: [{ version: 2, prefix: "open/ds-1/2/" }] });
  }
  if (path.startsWith("/api/datasets/")) return Response.json({}, { status: 404 });
  if (path === "/api/search") return Response.json({ total: 0, rows: [], facets: {} });
  return new Promise(() => {});
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(answer));
  vi.mocked(signedInEmail).mockReturnValue(null);
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** A link the test presses to navigate inside the app, as a reader following a link would. */
function GoTo() {
  const navigate = useNavigate();
  return (
    <button type="button" data-testid="go" onClick={(event) => navigate(event.currentTarget.value)}>
      go
    </button>
  );
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
      <GoTo />
    </MemoryRouter>,
  );
}

test.each([
  ["/", "Search the archive", `Search · ${NAME}`],
  ["/datasets/ds-1", "Lake levels", `Lake levels · ${NAME}`],
  ["/datasets/ds-1/v2", "Lake levels", `Lake levels · ${NAME}`],
  ["/datasets/missing", "Dataset not found", `Not found · ${NAME}`],
  ["/about", "About the archive", `About · ${NAME}`],
  ["/auth/callback", "Signing in", `Signing in · ${NAME}`],
  ["/nowhere", "Page not found", `Not found · ${NAME}`],
  ["/datasets/ds-1/latest", "Page not found", `Not found · ${NAME}`],
])("%s renders its heading and title", async (path, heading, title) => {
  renderAt(path);

  expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeDefined();
  await waitFor(() => expect(document.title).toBe(title));
});

test("the masthead shows the archive's name, Browse and About the archive; the footer the publisher", () => {
  renderAt("/");

  const banner = screen.getByRole("banner");
  expect(banner.textContent).toContain(NAME);
  expect(screen.getByRole("link", { name: "Browse" }).getAttribute("href")).toBe("/");
  expect(screen.getByRole("link", { name: "About the archive" }).getAttribute("href")).toBe(
    "/about",
  );
  expect(screen.getByRole("contentinfo").textContent).toContain(NAME);
});

test("the masthead shows the brand's logo", () => {
  renderAt("/");

  const logo = screen.getByRole("banner").querySelector("img");
  expect(logo?.getAttribute("src")).toMatch(/^\/brand\/logo-[0-9a-f]{8}\.svg$/);
  expect(logo?.getAttribute("alt")).toBe("");
});

test("the about page shows the intro and the contact", async () => {
  renderAt("/about");

  await screen.findByRole("heading", { level: 1, name: "About the archive" });
  expect(screen.getByText(/shares the data behind its field studies/)).toBeDefined();
  const main = within(screen.getByRole("main"));
  expect(main.getByRole("link", { name: "archive-admin@example.org" }).getAttribute("href")).toBe(
    "mailto:archive-admin@example.org",
  );
});

test("the skip link leads the page and reaches main", () => {
  renderAt("/");

  const links = screen.getAllByRole("link");
  expect(links[0]?.textContent).toBe("Skip to content");
  const target = links[0]?.getAttribute("href")?.slice(1) ?? "";
  const main = document.getElementById(target);
  expect(main?.tagName).toBe("MAIN");
  expect(main?.getAttribute("tabindex")).toBe("-1");
});

test("after navigating, focus is on the new page's h1", async () => {
  renderAt("/");
  await screen.findByRole("heading", { level: 1, name: "Search the archive" });
  expect(document.activeElement).toBe(document.body);

  const go = screen.getByTestId("go") as HTMLButtonElement;
  go.value = "/datasets/ds-1";
  act(() => go.click());

  const heading = await screen.findByRole("heading", { level: 1, name: "Lake levels" });
  await waitFor(() => expect(document.activeElement).toBe(heading));

  go.value = "/about";
  fireEvent.click(go);
  const about = await screen.findByRole("heading", { level: 1, name: "About the archive" });
  await waitFor(() => expect(document.activeElement).toBe(about));
});

test.each(["/", "/datasets/ds-1", "/about", "/nowhere", "/datasets/missing"])(
  "an axe check of %s finds no violations",
  async (path) => {
    const { container } = renderAt(path);
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(screen.queryByText(/Loading/)).toBeNull());

    const results = await axe.run(container);
    expect(results.violations).toEqual([]);
  },
);

test("signed in, the header names the reader with Sign out and Add a passkey", () => {
  vi.mocked(signedInEmail).mockReturnValue("reader@example.org");
  renderAt("/");

  const banner = within(screen.getByRole("banner"));
  expect(banner.getByText("Signed in as reader@example.org")).toBeDefined();
  fireEvent.click(banner.getByRole("button", { name: "Add a passkey" }));
  expect(addPasskey).toHaveBeenCalledWith("/");
  fireEvent.click(banner.getByRole("button", { name: "Sign out" }));
  expect(signOut).toHaveBeenCalled();
});

test("signed out, the header says nothing of an account", () => {
  renderAt("/");

  expect(within(screen.getByRole("banner")).queryByRole("button", { name: "Sign out" })).toBeNull();
});

test("a failed sign-in offers Back to the dataset and Try again", async () => {
  vi.mocked(completeSignIn).mockRejectedValueOnce(new Error("no state"));
  sessionStorage.setItem("sign-in-return-to", "/datasets/ds-1");
  renderAt("/auth/callback");

  const back = await screen.findByRole("link", { name: "Back to the dataset" });
  expect(back.getAttribute("href")).toBe("/datasets/ds-1");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(signIn).toHaveBeenCalledWith("/datasets/ds-1");
});

test("back from adding a passkey, with no code, the callback says Passkey added and offers Sign in", async () => {
  vi.mocked(completeSignIn).mockClear();
  vi.mocked(signIn).mockClear();
  sessionStorage.setItem("passkey-add-return-to", "/datasets/ds-1");
  renderAt("/auth/callback");

  expect(await screen.findByRole("heading", { level: 1, name: "Passkey added" })).toBeDefined();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(completeSignIn).not.toHaveBeenCalled();
  const back = screen.getByRole("link", { name: "Back to the dataset" });
  expect(back.getAttribute("href")).toBe("/datasets/ds-1");
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(signIn).toHaveBeenCalledWith("/datasets/ds-1");
  await waitFor(() => expect(sessionStorage.getItem("passkey-add-return-to")).toBeNull());
});

test("a callback with no code and no passkey flag still says sign-in didn't finish", async () => {
  vi.mocked(completeSignIn).mockRejectedValueOnce(new Error("no code"));
  renderAt("/auth/callback");

  expect((await screen.findByRole("alert")).textContent).toBe("Sign-in didn't finish.");
  expect(screen.queryByText("Passkey added")).toBeNull();
});
