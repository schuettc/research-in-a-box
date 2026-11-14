import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";
import { forgetPeople } from "../People";
import { event, item } from "../test-fixtures";
import { ReviewQueue } from "./ReviewQueue";

vi.mock("../auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../auth")>()),
  apiToken: vi.fn(() => "token"),
  signedInSub: vi.fn(() => "cur-1"),
  groups: vi.fn(() => CURATOR),
}));
const CURATOR = ["curator"];

const EMAILS: Record<string, string> = {
  "con-3": "contributor@example.org",
  "cur-1": "curator@example.org",
  "cur-2": "second@example.org",
};

let fetchMock: Mock;

beforeEach(() => {
  forgetPeople();
  fetchMock = vi.fn(async (url: string) => {
    const parsed = new URL(url, "https://site");
    const path = parsed.pathname;
    if (parsed.host === "staging.example")
      return Response.json({ title: `Title of ${path.split("/")[2]}` });
    if (path === "/api/submissions") {
      const status = parsed.searchParams.get("status");
      if (status === "needs-changes") {
        return Response.json({
          submissions: [item({ submissionId: "s-9", status: "needs-changes", submitter: "con-3" })],
        });
      }
      return Response.json({
        submissions: [
          item({
            submissionId: "s-1",
            submitter: "con-3",
            newVersion: true,
            stale: true,
            approvals: ["cur-2"],
          }),
          item({ submissionId: "s-2", submitter: "con-3", datasetId: "lake-levels" }),
        ],
      });
    }
    if (path === "/api/people") {
      const people: Record<string, { email: string }> = {};
      for (const sub of parsed.searchParams.getAll("sub")) people[sub] = { email: EMAILS[sub]! };
      return Response.json({ people });
    }
    const match = /^\/api\/submissions\/([^/]+)(\/files)?$/.exec(path);
    if (match?.[2]) {
      return Response.json({
        round: 1,
        files: [
          {
            path: "datapackage.json",
            size: 10,
            sha256: "a".repeat(64),
            url: `https://staging.example/held/${match[1]}/datapackage.json`,
          },
        ],
      });
    }
    if (match) {
      const two = match[1] === "s-1";
      return Response.json({
        submission: item({ submissionId: match[1] }),
        events: [
          event("entered-review", {
            outcome: two ? "two" : "one",
            audience: two ? "cur-1" : "all",
          }),
        ],
      });
    }
    return Response.json({}, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderQueue(path = "/review") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ReviewQueue />
    </MemoryRouter>,
  );
}

const statusAsked = () =>
  fetchMock.mock.calls
    .map(([url]) => new URL(String(url), "https://site"))
    .filter((url) => url.pathname === "/api/submissions")
    .map((url) => url.searchParams.get("status"));

test("the queue lists what is in review, each row saying kind, stale, curators needed and who it's assigned to", async () => {
  renderQueue();

  const first = (await screen.findByRole("link", { name: "Title of s-1" })).closest("tr")!;
  expect(statusAsked()).toEqual(["in-review"]);
  expect(first.querySelector("a")?.getAttribute("href")).toBe("/review/s-1");
  const row = within(first);
  expect(row.getByText("New version")).toBeDefined();
  expect(row.getByText("Stale")).toBeDefined();
  await waitFor(() => expect(first.textContent).toContain("1 of 2 approved"));
  await waitFor(() => expect(first.textContent).toContain("contributor@example.org"));
  expect(first.textContent).toContain("you");

  const second = (await screen.findByRole("link", { name: "Title of s-2" })).closest("tr")!;
  expect(within(second).getByText("New dataset")).toBeDefined();
  await waitFor(() => expect(second.textContent).toContain("0 of 1 approved"));
  expect(second.textContent).toContain("Any curator");
  expect(within(second).queryByText("Stale")).toBeNull();
});

test("the filter shows another status", async () => {
  renderQueue();
  await screen.findByRole("link", { name: "Title of s-1" });

  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "needs-changes" } });

  expect(await screen.findByRole("link", { name: "stream-temperature-sample" })).toBeDefined();
  expect(statusAsked()).toEqual(["in-review", "needs-changes"]);
});

test("an axe check of the queue finds no violations", async () => {
  const { container } = renderQueue();
  await screen.findByRole("link", { name: "Title of s-1" });

  expect((await axe.run(container)).violations).toEqual([]);
});
