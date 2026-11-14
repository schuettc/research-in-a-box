import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AppRoutes } from "./App";

const MANIFEST = { id: "ds-1", title: "Lake levels", "archive:access": "open" };

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
  return new Promise(() => {});
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(answer));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

test.each([
  ["/", "Search the archive"],
  ["/datasets/ds-1", "Lake levels"],
  ["/datasets/ds-1/v2", "Lake levels"],
  ["/auth/callback", "Signing in"],
  ["/nowhere", "Page not found"],
  ["/datasets/ds-1/latest", "Page not found"],
])("%s renders its heading", async (path, heading) => {
  renderAt(path);

  expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeDefined();
});

test("the header shows the archive's publisher", () => {
  renderAt("/");

  expect(screen.getByRole("banner").textContent).toContain("Invented Research Cooperative");
});
