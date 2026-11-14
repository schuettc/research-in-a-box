import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter, Route, Routes, useParams } from "react-router";
import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";
import { FakeXhr, sampleFiles } from "../test-fixtures";
import { Submit } from "./Submit";

vi.mock("../auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../auth")>()),
  apiToken: vi.fn(() => "token"),
  signedInSub: vi.fn(() => "me-1"),
}));

const STAGING = "https://staging.example/incoming/s-1/1/";
const b64 = (hex: string) =>
  btoa(String.fromCharCode(...hex.match(/../g)!.map((h) => parseInt(h, 16))));

let fetchMock: Mock;
let progressAtSubmit: string | null = null;
let created: { files: { path: string; size: number; sha256: string }[]; datasetId: string } | null;

beforeEach(() => {
  FakeXhr.sent = [];
  FakeXhr.status = 200;
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  created = null;
  progressAtSubmit = null;
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, "https://site").pathname;
    if (path === "/api/datasets/stream-temperature-sample")
      return Response.json({}, { status: 404 });
    if (path === "/api/submissions" && init?.method === "POST") {
      created = JSON.parse(String(init.body));
      return Response.json(
        {
          submissionId: "s-1",
          round: 1,
          uploads: created!.files.map((file) => ({
            path: file.path,
            url: STAGING + file.path,
            headers: { "x-amz-checksum-sha256": b64(file.sha256) },
          })),
        },
        { status: 201 },
      );
    }
    if (path === "/api/submissions/s-1/submit") {
      progressAtSubmit = screen
        .getByRole("progressbar", { name: "All files" })
        .getAttribute("value");
      return Response.json({ submissionId: "s-1", round: 1, status: "checking" }, { status: 202 });
    }
    return Response.json({ error: "unexpected" }, { status: 400 });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function Arrived() {
  const { id } = useParams();
  return <p>Arrived at {id}</p>;
}

function renderSubmit() {
  return render(
    <MemoryRouter initialEntries={["/submit"]}>
      <Routes>
        <Route path="/submit" element={<Submit />} />
        <Route path="/submissions/:id" element={<Arrived />} />
      </Routes>
    </MemoryRouter>,
  );
}

function choose(files: File[]) {
  fireEvent.change(screen.getByLabelText("Choose folder"), { target: { files } });
}

test("the sample folder is checked, created as a new dataset, uploaded with each checksum and submitted", async () => {
  renderSubmit();
  choose(sampleFiles());

  expect(await screen.findByText("New dataset")).toBeDefined();
  expect(screen.getByText("Stream temperature at three invented sites")).toBeDefined();
  expect(screen.getByText(/_build\/make\.py/)).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Upload and submit" }));

  expect(await screen.findByText("Arrived at s-1")).toBeDefined();
  expect(created?.datasetId).toBe("stream-temperature-sample");
  expect(created?.files.map((file) => file.path)).toContain("checksums.sha256");
  expect(FakeXhr.sent).toHaveLength(created!.files.length);
  for (const sent of FakeXhr.sent) {
    const file = created!.files.find((f) => STAGING + f.path === sent.url)!;
    expect(sent.method).toBe("PUT");
    expect(sent.headers["x-amz-checksum-sha256"]).toBe(b64(file.sha256));
  }
  expect(progressAtSubmit).toBe("100");
});

test("a folder that is already published reads as a new version", async () => {
  fetchMock.mockImplementationOnce(async () => Response.json({ id: "stream-temperature-sample" }));
  renderSubmit();
  choose(sampleFiles());

  expect(await screen.findByText(/New version of/)).toBeDefined();
});

test("a folder without checksums.sha256 is refused before anything is sent", async () => {
  renderSubmit();
  choose(sampleFiles({}, ["checksums.sha256"]));

  expect((await screen.findByRole("alert")).textContent).toMatch(/no checksums\.sha256/);
  expect(screen.queryByRole("button", { name: "Upload and submit" })).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("a changed file is named and stops the submission", async () => {
  renderSubmit();
  choose(sampleFiles({ "data/logger.csv": "changed\n" }));

  expect((await screen.findByRole("alert")).textContent).toContain(
    "data/logger.csv doesn't match its checksum",
  );
  expect(screen.queryByRole("button", { name: "Upload and submit" })).toBeNull();
});

test("an upload S3 refuses says so and offers Try again", async () => {
  FakeXhr.status = 403;
  renderSubmit();
  choose(sampleFiles());
  fireEvent.click(await screen.findByRole("button", { name: "Upload and submit" }));

  expect((await screen.findByRole("alert")).textContent).toMatch(/upload/i);
  expect(screen.getByRole("button", { name: "Try again" })).toBeDefined();
});

test("an axe check of the choose and ready steps finds no violations", async () => {
  const { container } = renderSubmit();
  expect((await axe.run(container)).violations).toEqual([]);

  choose(sampleFiles());
  await screen.findByText("New dataset");
  await waitFor(async () => expect((await axe.run(container)).violations).toEqual([]));
});
