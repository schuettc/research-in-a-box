import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";
import type { SubmissionRead } from "../api";
import { event, FakeXhr, item, REPORT, sampleFiles } from "../test-fixtures";
import { Submission } from "./Submission";

vi.mock("../auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../auth")>()),
  apiToken: vi.fn(() => "token"),
  signedInSub: vi.fn(() => "me-1"),
  groups: vi.fn(() => CONTRIBUTOR),
}));
const CONTRIBUTOR = ["contributor"];

const REPORT_URL = "https://staging.example/reports/s-1/1.json?sig";

let fetchMock: Mock;
let reads: SubmissionRead[];

function answer(...answers: SubmissionRead[]) {
  reads = answers;
}

beforeEach(() => {
  FakeXhr.sent = [];
  FakeXhr.status = 200;
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  answer({
    submission: item(),
    events: [event("created", { actor: "me-1" })],
    reportUrl: REPORT_URL,
  });
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === REPORT_URL) return Response.json(REPORT);
    const path = new URL(url, "https://site").pathname;
    if (path === "/api/submissions/s-1")
      return Response.json(reads.length > 1 ? reads.shift() : reads[0]);
    if (path === "/api/submissions/s-1/uploads") {
      const { files } = JSON.parse(String(init?.body)) as { files: { path: string }[] };
      return Response.json({
        submissionId: "s-1",
        round: 2,
        uploads: files.map((file) => ({
          path: file.path,
          url: `https://staging.example/incoming/s-1/2/${file.path}`,
          headers: { "x-amz-checksum-sha256": "c2lnbg==" },
        })),
      });
    }
    if (path === "/api/submissions/s-1/submit") {
      return Response.json({ submissionId: "s-1", round: 2, status: "checking" }, { status: 202 });
    }
    if (path.startsWith("/api/datasets/")) return Response.json({}, { status: 404 });
    return Response.json({ error: "unexpected" }, { status: 400 });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function renderPage() {
  return render(
    <MemoryRouter>
      <Submission id="s-1" />
    </MemoryRouter>,
  );
}

const reads$ = () =>
  fetchMock.mock.calls.filter(
    ([url]) => new URL(String(url), "https://site").pathname === "/api/submissions/s-1",
  ).length;

test("the page says where the submission stands, in one line", async () => {
  renderPage();

  expect(await screen.findByText("Waiting for a curator")).toBeDefined();
  expect(
    screen.getByRole("heading", { level: 1, name: "stream-temperature-sample" }),
  ).toBeDefined();
});

test("findings are grouped error, warning, note, each with its target and suggested fix", async () => {
  renderPage();

  const groups = await screen.findAllByRole("heading", { level: 3 });
  expect(groups.map((heading) => heading.textContent)).toEqual([
    "Errors (1)",
    "Warnings (1)",
    "Notes (1)",
  ]);
  const errors = screen.getByRole("list", { name: "Errors" });
  expect(errors.textContent).toContain("Column site_id has values outside its codelist.");
  expect(errors.textContent).toContain("logger › site_id");
  expect(errors.textContent).toContain("Add S9 and S0 to the site codes.");
  expect(errors.textContent).toContain("rows 14, 98");
  expect(screen.getByRole("list", { name: "Notes" }).textContent).toContain("docs/methods.md");
  expect(screen.getByText(/87%/)).toBeDefined();
});

test("on changes requested, the curator's note shows and Resubmit sends round 2's files to its new links", async () => {
  answer({
    submission: item({ status: "needs-changes", waiting: true }),
    events: [
      event("created", { actor: "me-1" }),
      event("decided", { actor: "cur-1", decision: "request-changes", note: "Give the units." }),
    ],
    reportUrl: REPORT_URL,
  });
  renderPage();

  const said = await screen.findByText("The curator's note");
  expect(said.nextElementSibling?.textContent).toBe("Give the units.");
  fireEvent.click(screen.getByRole("button", { name: "Resubmit" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.change(within(dialog).getByLabelText("Choose folder"), {
    target: { files: sampleFiles() },
  });
  fireEvent.click(await within(dialog).findByRole("button", { name: "Upload and submit" }));

  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/s-1/submit"))).toBe(true),
  );
  expect(FakeXhr.sent.length).toBeGreaterThan(0);
  expect(
    FakeXhr.sent.every((sent) => sent.url.startsWith("https://staging.example/incoming/s-1/2/")),
  ).toBe(true);
  const uploads = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/s-1/uploads"));
  expect(uploads?.[1]?.method).toBe("POST");
});

test("while the pipeline isn't ready for the next round, Resubmit waits", async () => {
  answer({
    submission: item({ status: "needs-changes", waiting: false }),
    events: [event("decided", { actor: "cur-1", decision: "request-changes", note: "Fix it." })],
    reportUrl: REPORT_URL,
  });
  renderPage();

  const button = await screen.findByRole("button", { name: "Resubmit" });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText(/getting ready for your next round/)).toBeDefined();
});

test("a round-1 draft whose upload didn't finish can choose the folder again for new links", async () => {
  answer({
    submission: item({ status: "draft", reportKey: null }),
    events: [event("created")],
    reportUrl: null,
  });
  renderPage();

  expect(await screen.findByRole("button", { name: "Choose the folder again" })).toBeDefined();
});

test("it reloads every 10 s while checking, and stops once published", async () => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  answer(
    { submission: item({ status: "checking" }), events: [], reportUrl: null },
    { submission: item({ status: "published" }), events: [], reportUrl: null },
  );
  renderPage();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(reads$()).toBe(1);

  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_000);
  });
  expect(reads$()).toBe(2);
  expect(screen.getByText("Published")).toBeDefined();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_000);
  });
  expect(reads$()).toBe(2);
});

test("the history lists each event once, the reader as you", async () => {
  const created = event("created", { actor: "me-1" });
  answer({
    submission: item(),
    events: [created, event("checked", { errors: 0, warnings: 1, notes: 0 }), { ...created }],
    reportUrl: null,
  });
  renderPage();

  const history = await screen.findByRole("list", { name: "History" });
  expect(within(history).getAllByRole("listitem")).toHaveLength(2);
  expect(history.textContent).toContain("Created by you");
});

test("an axe check of the submission page finds no violations", async () => {
  const { container } = renderPage();
  await screen.findByText("Errors (1)");

  expect((await axe.run(container)).violations).toEqual([]);
});
