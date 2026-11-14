import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";
import type { SubmissionRead } from "../api";
import { forgetPeople } from "../People";
import { event, item, REPORT } from "../test-fixtures";
import { Review } from "./Review";

vi.mock("../auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../auth")>()),
  apiToken: vi.fn(() => "token"),
  signedInSub: vi.fn(() => "cur-1"),
  groups: vi.fn(() => CURATOR),
}));
const CURATOR = ["curator"];

const REPORT_URL = "https://staging.example/reports/s-1/1.json?sig";
const CSV = "site,when,temp\nS1,2024-06-01T00:00,11.5\nS2,2024-06-01T00:00,12.25\n";

let fetchMock: Mock;
let read: SubmissionRead;
let decision: (() => Response) | null;

beforeEach(() => {
  forgetPeople();
  decision = null;
  read = {
    submission: item({ submitter: "con-3" }),
    events: [
      event("created", { actor: "con-3" }),
      event("entered-review", { outcome: "one", audience: "all" }),
    ],
    reportUrl: REPORT_URL,
  };
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === REPORT_URL) return Response.json(REPORT);
    const parsed = new URL(url, "https://site");
    if (parsed.host === "staging.example") {
      if (parsed.pathname.endsWith("datapackage.json"))
        return Response.json({ title: "Lake levels" });
      // A long file: the range answer stops partway through a line.
      return new Response(CSV + "S3,2024-06-01T00:00,1", { status: 206 });
    }
    const path = parsed.pathname;
    if (path === "/api/people") {
      return Response.json({ people: { "con-3": { email: "contributor@example.org" } } });
    }
    if (path === "/api/submissions/s-1") return Response.json(read);
    if (path === "/api/submissions/s-1/files") {
      return Response.json({
        round: 1,
        files: [
          {
            path: "datapackage.json",
            size: 10,
            sha256: "a".repeat(64),
            url: "https://staging.example/held/datapackage.json",
          },
          {
            path: "data/logger.csv",
            size: 70000,
            sha256: "b".repeat(64),
            url: "https://staging.example/held/data/logger.csv",
          },
        ],
      });
    }
    if (path === "/api/submissions/s-1/decision") {
      if (decision) return decision();
      const body = JSON.parse(String(init?.body)) as { decision: string };
      return Response.json({ submissionId: "s-1", decision: body.decision }, { status: 202 });
    }
    return Response.json({}, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderReview() {
  return render(
    <MemoryRouter>
      <Review id="s-1" />
    </MemoryRouter>,
  );
}

const decisions = () =>
  fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith("/s-1/decision"))
    .map(([, init]) => JSON.parse(String((init as RequestInit).body)) as unknown);

test("the review page shows the title, the submitter's email, the findings, the held files and the history", async () => {
  renderReview();

  expect(await screen.findByRole("heading", { level: 1, name: "Lake levels" })).toBeDefined();
  expect(await screen.findByText("Errors (1)")).toBeDefined();
  const files = await screen.findByRole("list", { name: "Held files" });
  expect(
    within(files).getByRole("link", { name: "Download data/logger.csv" }).getAttribute("href"),
  ).toBe("https://staging.example/held/data/logger.csv");
  await waitFor(() =>
    expect(screen.getByRole("list", { name: "History" }).textContent).toContain(
      "Created by contributor@example.org",
    ),
  );
});

test("Request changes posts its note", async () => {
  renderReview();
  fireEvent.click(await screen.findByRole("button", { name: "Request changes" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText(/Note to the contributor/), {
    target: { value: "Give the units." },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Request changes" }));

  await waitFor(() =>
    expect(decisions()).toEqual([{ decision: "request-changes", note: "Give the units." }]),
  );
});

test("Request changes and Reject can't be confirmed without a note; Approve can", async () => {
  renderReview();
  for (const name of ["Request changes", "Reject"]) {
    fireEvent.click(await screen.findByRole("button", { name }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/Note to the contributor/), {
      target: { value: "  " },
    });
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  }
  fireEvent.click(screen.getByRole("button", { name: "Approve" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.click(within(dialog).getByRole("button", { name: "Approve" }));

  await waitFor(() => expect(decisions()).toEqual([{ decision: "approve" }]));
});

test("after a first approval of a two-curator review, Approve is disabled for the curator who gave it", async () => {
  read = {
    ...read,
    submission: item({ submitter: "con-3", approvals: ["cur-1"], waiting: true }),
    events: [
      event("entered-review", { outcome: "two", audience: "all" }),
      event("decided", { actor: "cur-1", decision: "approve" }),
    ],
  };
  renderReview();

  expect(await screen.findByText(/waits for a second curator/)).toBeDefined();
  expect((screen.getByRole("button", { name: "Approve" }) as HTMLButtonElement).disabled).toBe(
    true,
  );
  expect(
    (screen.getByRole("button", { name: "Request changes" }) as HTMLButtonElement).disabled,
  ).toBe(false);
});

test("after approving a one-curator review, the page says it's approved and being published, not that it waits for a second curator", async () => {
  read = {
    ...read,
    submission: item({ submitter: "con-3", approvals: ["cur-1"], waiting: false }),
    events: [
      event("entered-review", { outcome: "one", audience: "all" }),
      event("decided", { actor: "cur-1", decision: "approve" }),
    ],
  };
  renderReview();

  expect(await screen.findByText(/You approved it; it's being published/)).toBeDefined();
  expect(screen.queryByText(/second curator/)).toBeNull();
});

test("while the pipeline isn't ready for a decision, the decision buttons wait", async () => {
  read = {
    ...read,
    submission: item({ submitter: "con-3", approvals: ["cur-2"], waiting: false }),
  };
  renderReview();

  expect(await screen.findByText(/getting ready for the next decision/)).toBeDefined();
  expect((screen.getByRole("button", { name: "Approve" }) as HTMLButtonElement).disabled).toBe(
    true,
  );
});

test("a decision answered 409 shows the API's words and Reload", async () => {
  decision = () =>
    Response.json(
      { error: "a second approval must come from a different curator" },
      { status: 409 },
    );
  renderReview();
  fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
  fireEvent.click(
    within(await screen.findByRole("dialog")).getByRole("button", { name: "Approve" }),
  );

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("a second approval must come from a different curator");
  const reads = () =>
    fetchMock.mock.calls.filter(([url]) => String(url) === "/api/submissions/s-1").length;
  const before = reads();
  fireEvent.click(screen.getByRole("button", { name: "Reload" }));
  await waitFor(() => expect(reads()).toBe(before + 1));
});

test("the preview of a CSV shows its first rows, read by range", async () => {
  renderReview();
  fireEvent.click(await screen.findByRole("button", { name: "Preview data/logger.csv" }));

  const dialog = await screen.findByRole("dialog");
  const table = await within(dialog).findByRole("table");
  const rows = within(table)
    .getAllByRole("row")
    .map((row) => row.textContent);
  expect(rows).toEqual(["sitewhentemp", "S12024-06-01T00:0011.5", "S22024-06-01T00:0012.25"]);
  const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("logger.csv"))!;
  expect(new Headers((init as RequestInit).headers).get("Range")).toBe("bytes=0-65535");
});

test("an axe check of the review page and its decision modal finds no violations", async () => {
  const { container } = renderReview();
  await screen.findByText("Errors (1)");
  await screen.findByRole("list", { name: "Held files" });
  expect((await axe.run(container)).violations).toEqual([]);

  fireEvent.click(screen.getByRole("button", { name: "Reject" }));
  await screen.findByRole("dialog");
  expect((await axe.run(container)).violations).toEqual([]);
});
