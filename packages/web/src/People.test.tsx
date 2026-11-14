import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";
import { apiToken, groups, signedInSub } from "./auth";
import { forgetPeople, usePeople } from "./People";

vi.mock("./auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./auth")>()),
  signedInSub: vi.fn(() => "me-1"),
  groups: vi.fn(() => ["curator"]),
  apiToken: vi.fn(() => "token"),
}));

let fetchMock: Mock;

beforeEach(() => {
  forgetPeople();
  vi.mocked(signedInSub).mockReturnValue("me-1");
  vi.mocked(groups).mockReturnValue(["curator"]);
  vi.mocked(apiToken).mockReturnValue("token");
  fetchMock = vi.fn(async (url: string) => {
    const subs = new URL(url, "https://site").searchParams.getAll("sub");
    const people: Record<string, { email: string }> = {};
    for (const sub of subs) if (sub !== "gone-9") people[sub] = { email: `${sub}@example.org` };
    return Response.json({ people });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function Names({ subs }: { subs: string[] }) {
  const name = usePeople(subs);
  return (
    <ul>
      {subs.map((sub) => (
        <li key={sub} data-testid={sub}>
          {name(sub)}
        </li>
      ))}
    </ul>
  );
}

test("the people hook asks once for every id on the page and names the reader you", async () => {
  render(
    <>
      <Names subs={["me-1", "ann-2", "pipeline"]} />
      <Names subs={["bob-3", "ann-2"]} />
    </>,
  );

  await waitFor(() =>
    expect(screen.getAllByTestId("ann-2")[0]?.textContent).toBe("ann-2@example.org"),
  );
  expect(screen.getByTestId("bob-3").textContent).toBe("bob-3@example.org");
  expect(screen.getByTestId("me-1").textContent).toBe("you");
  expect(screen.getByTestId("pipeline").textContent).toBe("the archive");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(new URL(url, "https://site").pathname).toBe("/api/people");
  expect(new URL(url, "https://site").searchParams.getAll("sub").toSorted()).toEqual([
    "ann-2",
    "bob-3",
  ]);
  expect(new Headers(init.headers).get("Authorization")).toBe("Bearer token");
});

test("an id already looked up isn't asked for again, and an unknown one reads as someone", async () => {
  const { unmount } = render(<Names subs={["ann-2", "gone-9"]} />);
  await waitFor(() => expect(screen.getByTestId("ann-2").textContent).toBe("ann-2@example.org"));
  await waitFor(() => expect(screen.getByTestId("gone-9").textContent).toBe("someone"));
  unmount();

  render(<Names subs={["ann-2"]} />);
  expect(screen.getByTestId("ann-2").textContent).toBe("ann-2@example.org");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("more than 50 ids go in batches of 50", async () => {
  const subs = Array.from({ length: 120 }, (_, n) => `p-${n}`);
  render(<Names subs={subs} />);

  await waitFor(() => expect(screen.getByTestId("p-119").textContent).toBe("p-119@example.org"));
  const sizes = fetchMock.mock.calls.map(
    ([url]) => new URL(String(url), "https://site").searchParams.getAll("sub").length,
  );
  expect(sizes).toEqual([50, 50, 20]);
});

test("a contributor can't look people up: others read as a curator, and nothing is asked", () => {
  vi.mocked(groups).mockReturnValue(["contributor"]);
  render(<Names subs={["me-1", "ann-2"]} />);

  expect(screen.getByTestId("me-1").textContent).toBe("you");
  expect(screen.getByTestId("ann-2").textContent).toBe("a curator");
  expect(fetchMock).not.toHaveBeenCalled();
});
