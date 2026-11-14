import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import type { Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";
import type { DatasetAnswer, VersionAnswer, VersionsAnswer } from "../api";
import type { Manifest } from "../generated/manifest";
import { mount } from "../main";
import { Dataset } from "./Dataset";

const SAMPLE = join(import.meta.dirname, "../../../../examples/sample-package");
const MANIFEST = JSON.parse(readFileSync(join(SAMPLE, "datapackage.json"), "utf-8")) as Manifest;
const ID = "stream-temperature-sample";

const DATASET: DatasetAnswer = {
  id: ID,
  title: MANIFEST.title ?? "",
  access: "open",
  currentVersion: 1,
  prefix: `open/${ID}/1/`,
  manifest: MANIFEST,
  files: [],
  project: null,
};
const VERSION: VersionAnswer = {
  version: 1,
  prefix: `open/${ID}/1/`,
  manifest: MANIFEST,
  files: [],
  publishedAt: "2024-07-01T12:00:00Z",
};
const VERSIONS: VersionsAnswer = {
  versions: [
    { version: 1, prefix: `open/${ID}/1/` },
    { version: 2, prefix: `open/${ID}/2/` },
  ],
};

let fetchMock: Mock;

function apiAnswers(): Mock {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, "https://site").pathname;
    if (init?.method === "POST") return new Response(null, { status: 204 });
    if (path === `/api/datasets/${ID}`) return Response.json(DATASET);
    if (path === `/api/datasets/${ID}/versions/1`) return Response.json(VERSION);
    if (path === `/api/datasets/${ID}/versions`) return Response.json(VERSIONS);
    return Response.json({ message: "not found" }, { status: 404 });
  });
}

function renderDataset(version?: number) {
  return render(
    <MemoryRouter>
      <Dataset id={ID} version={version} />
    </MemoryRouter>,
  );
}

/** The Files table's row whose first cell is the title. */
function rowOf(files: HTMLElement, title: string): HTMLElement | undefined {
  return [...files.querySelectorAll("tbody tr")].find(
    (row) => row.querySelector("td")?.textContent === title,
  ) as HTMLElement | undefined;
}

async function filesTable(): Promise<HTMLElement> {
  await screen.findByRole("heading", { level: 1, name: MANIFEST.title ?? "" });
  return screen.getByRole("table", { name: "Files" });
}

beforeEach(() => {
  fetchMock = apiAnswers();
  vi.stubGlobal("fetch", fetchMock);
  sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

test("every resource shows with its kind, and each file has its download", async () => {
  renderDataset();
  const files = await filesTable();

  for (const resource of MANIFEST.resources ?? []) {
    const row = rowOf(files, resource.title ?? resource.name);
    expect(row?.textContent).toContain(resource["archive:kind"] ?? "");
  }
  const logger = within(files).getByRole("link", { name: "Download Logger readings" });
  expect(logger.getAttribute("href")).toBe(`/data/${ID}/1/data/logger.csv`);
  const sites = rowOf(files, "Sites");
  expect(sites?.textContent).toContain("4 files");
  expect(within(files).getByRole("link", { name: "Download data/sites/sites.dbf" })).toBeDefined();
  const linked = within(files).getByRole("link", { name: "Open link Discharge" });
  expect(linked.getAttribute("href")).toBe("https://example.org/stream-temperature/discharge.csv");
});

test("the citation is the README's with the versioned URL, and Copy writes it", async () => {
  const writeText = vi.fn(async () => {});
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  renderDataset();
  await filesTable();

  const readme = readFileSync(join(SAMPLE, "README.md"), "utf-8").split("\n");
  const expected = `${readme[readme.indexOf("## Citation") + 2]} ${location.origin}/datasets/${ID}/v1`;
  const section = screen.getByRole("region", { name: "Cite this dataset" });
  expect(within(section).getByText(expected)).toBeDefined();
  fireEvent.click(within(section).getByRole("button", { name: "Copy" }));

  await waitFor(() => expect(writeText).toHaveBeenCalledWith(expected));
});

test("the page shows the About facts and each table's columns", async () => {
  renderDataset();
  await filesTable();

  const about = screen.getByRole("region", { name: "About" });
  for (const text of ["Ada Invented", "CC-BY-4.0", "stream temperature", "2024-06-01 to ongoing"]) {
    expect(about.textContent).toContain(text);
  }
  const logger = screen.getByRole("table", { name: "Columns of Logger readings" });
  const battery = within(logger).getByText("battery_v").closest("tr");
  expect(battery?.textContent).toContain("No description");
  const condition = within(logger).getByText("condition").closest("tr");
  expect(condition?.textContent).toContain("condition-codes");
});

test("the versioned route shows a note linking to the newer version", async () => {
  renderDataset(1);

  const note = await screen.findByText(/A newer version of this dataset exists/);
  expect(within(note).getByRole("link").getAttribute("href")).toBe(`/datasets/${ID}/v2`);
  expect(screen.getByText("Published 2024-07-01")).toBeDefined();
});

test("the usage panel appears after a download and sends the answers", async () => {
  renderDataset();
  const files = await filesTable();
  expect(screen.queryByRole("region", { name: /how will you use this data/ })).toBeNull();

  fireEvent.click(within(files).getByRole("link", { name: "Download Logger readings" }));
  const panel = screen.getByRole("region", { name: /how will you use this data/ });
  fireEvent.change(within(panel).getByLabelText("Kind of organisation"), {
    target: { value: "university" },
  });
  fireEvent.change(within(panel).getByLabelText("Purpose"), { target: { value: "teaching" } });
  fireEvent.change(within(panel).getByLabelText("Note"), { target: { value: "A class" } });
  fireEvent.click(within(panel).getByRole("button", { name: "Send" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
  expect(url).toBe(`/api/datasets/${ID}/usage`);
  expect(init.method).toBe("POST");
  expect(JSON.parse(String(init.body))).toEqual({
    organisation: "university",
    purpose: "teaching",
    note: "A class",
  });
  expect(await screen.findByText("Thank you.")).toBeDefined();
});

test("after No thanks the usage panel stays gone for the visit", async () => {
  renderDataset();
  const files = await filesTable();
  const download = within(files).getByRole("link", { name: "Download Logger readings" });

  fireEvent.click(download);
  fireEvent.click(screen.getByRole("button", { name: "No thanks" }));
  expect(screen.queryByRole("region", { name: /how will you use this data/ })).toBeNull();
  fireEvent.click(download);

  expect(screen.queryByRole("region", { name: /how will you use this data/ })).toBeNull();
  cleanup();
  renderDataset();
  fireEvent.click(
    within(await filesTable()).getByRole("link", { name: "Download Logger readings" }),
  );
  expect(screen.queryByRole("region", { name: /how will you use this data/ })).toBeNull();
});

test("on a static dataset page, the static content stays when the API can't be reached", async () => {
  fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
  document.body.innerHTML = '<div id="app"><h1>Static title</h1></div>';
  history.pushState({}, "", `/datasets/${ID}`);
  const app = document.getElementById("app") as HTMLElement;

  let root: Root | undefined;
  await act(async () => {
    root = mount(app);
    await new Promise((resolve) => setTimeout(resolve, 50));
  });

  expect(fetchMock).toHaveBeenCalled();
  expect(app.innerHTML).toBe("<h1>Static title</h1>");
  act(() => root?.unmount());
});

test("on a static dataset page, the app renders over it once it has the dataset", async () => {
  document.body.innerHTML = '<div id="app"><h1>Static title</h1></div>';
  history.pushState({}, "", `/datasets/${ID}`);
  const app = document.getElementById("app") as HTMLElement;

  let root: Root | undefined;
  act(() => {
    root = mount(app);
  });

  await waitFor(() => expect(app.querySelector("h1")?.textContent).toBe(MANIFEST.title ?? ""));
  expect(app.textContent).not.toContain("Static title");
  act(() => root?.unmount());
});

test("an axe check of the page finds no violations", async () => {
  const { container } = renderDataset();
  const files = await filesTable();
  fireEvent.click(within(files).getByRole("link", { name: "Download Logger readings" }));

  const results = await axe.run(container);
  expect(results.violations).toEqual([]);
});
