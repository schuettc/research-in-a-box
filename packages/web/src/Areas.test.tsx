import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AppRoutes } from "./App";
import { groups, signedInEmail, signIn } from "./auth";

vi.mock("./auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./auth")>()),
  signedInEmail: vi.fn(() => null),
  signedInSub: vi.fn(() => null),
  groups: vi.fn(() => []),
  apiToken: vi.fn(() => null),
  signIn: vi.fn(async () => {}),
}));

beforeEach(() => {
  // The areas' own content waits on the API; these tests are about the frame and the gates.
  vi.stubGlobal(
    "fetch",
    vi.fn(() => new Promise(() => {})),
  );
  vi.mocked(signedInEmail).mockReturnValue(null);
  vi.mocked(groups).mockReturnValue([]);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

function signInAs(...roles: string[]) {
  vi.mocked(signedInEmail).mockReturnValue("reader@example.org");
  vi.mocked(groups).mockReturnValue(roles);
}

const navNames = () =>
  within(screen.getByRole("navigation", { name: "Main" }))
    .getAllByRole("link")
    .map((link) => link.textContent);

test.each([
  [[], ["Browse", "About the archive"]],
  [["contributor"], ["Browse", "About the archive", "Submit"]],
  [["curator"], ["Browse", "About the archive", "Review"]],
  [["admin"], ["Browse", "About the archive", "Settings"]],
  [
    ["contributor", "curator", "admin"],
    ["Browse", "About the archive", "Submit", "Review", "Settings"],
  ],
])("a reader in %j sees exactly %j", (roles, names) => {
  signInAs(...roles);
  renderAt("/about");

  expect(navNames()).toEqual(names);
});

test("signed out, the nav lists only Browse and About the archive", () => {
  renderAt("/about");

  expect(navNames()).toEqual(["Browse", "About the archive"]);
});

test("whatever the groups, Browse and About lead the nav and the account slot ends the masthead", () => {
  for (const roles of [[], ["contributor"], ["contributor", "curator", "admin"]]) {
    signInAs(...roles);
    const { unmount } = renderAt("/about");
    const inner = screen.getByRole("banner").querySelector(".inner");
    const children = [...(inner?.children ?? [])];
    expect(children.map((child) => child.className)).toEqual(["mark", "nav", "account"]);
    // The public links sit in their own slot ahead of the areas, so the areas never push them.
    const nav = screen.getByRole("navigation", { name: "Main" });
    const slots = [...nav.children].map((child) => child.className);
    expect(slots).toEqual(["nav-public", "nav-areas"]);
    unmount();
  }
});

test.each([
  ["/submit", "Submit a package", "contributor"],
  ["/submissions", "My submissions", "contributor"],
  ["/submissions/s-1", "Submission", "contributor"],
  ["/review", "Review queue", "curator"],
  ["/review/s-1", "Review", "curator"],
  ["/settings", "Settings", "admin"],
])("signed out, %s shows its heading and Sign in back to itself", (path, heading) => {
  renderAt(path);

  expect(screen.getByRole("heading", { level: 1, name: heading })).toBeDefined();
  const main = within(screen.getByRole("main"));
  fireEvent.click(main.getByRole("button", { name: "Sign in" }));
  expect(signIn).toHaveBeenCalledWith(path);
});

test.each([
  ["/submit", "Submit a package", "contributor"],
  ["/review", "Review queue", "curator"],
  ["/settings", "Settings", "admin"],
])(
  "signed in without the group, %s says it needs the %s role and whom to ask",
  (path, heading, role) => {
    signInAs();
    renderAt(path);

    expect(screen.getByRole("heading", { level: 1, name: heading })).toBeDefined();
    const main = screen.getByRole("main");
    expect(main.textContent).toContain(`needs the ${role} role`);
    expect(within(main).getByRole("link", { name: "archive-admin@example.org" })).toBeDefined();
    expect(within(main).queryByRole("button", { name: "Sign in" })).toBeNull();
  },
);

test.each(["/submit", "/review", "/settings"])(
  "an axe check of the gate at %s finds no violations",
  async (path) => {
    signInAs();
    const { container } = renderAt(path);

    const results = await axe.run(container);
    expect(results.violations).toEqual([]);
  },
);
