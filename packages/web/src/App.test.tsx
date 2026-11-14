import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter, useNavigate } from "react-router";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AppRoutes } from "./App";

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
  expect(logo?.getAttribute("src")).toBe("/brand/logo.svg");
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
