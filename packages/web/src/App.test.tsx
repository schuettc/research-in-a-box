import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AppRoutes } from "./App";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {})),
  );
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
  ["/datasets/ds-1", "Dataset"],
  ["/datasets/ds-1/v2", "Dataset"],
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
