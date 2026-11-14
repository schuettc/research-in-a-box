import { readFileSync } from "node:fs";
import { join } from "node:path";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import type { Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";
import type { DatasetAnswer, VersionAnswer, VersionsAnswer } from "../api";
import { apiToken, signIn } from "../auth";
import type { Manifest } from "../generated/manifest";
import { mount } from "../main";
import { Dataset } from "./Dataset";

vi.mock("../auth", () => ({
  apiToken: vi.fn(() => null),
  signIn: vi.fn(async () => {}),
  subscribe: vi.fn(() => () => {}),
  signedInEmail: vi.fn(() => null),
}));

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

const RESTRICTED_ID = "restricted-sample";
const RESTRICTED: DatasetAnswer = {
  ...DATASET,
  id: RESTRICTED_ID,
  access: "restricted",
  prefix: `restricted/${RESTRICTED_ID}/1/`,
  manifest: { ...MANIFEST, "archive:access": "restricted" },
};

let fetchMock: Mock;
let downloadStatus = 200;

function apiAnswers(): Mock {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, "https://site").pathname;
    if (init?.method === "POST") return new Response(null, { status: 204 });
    if (path === `/api/datasets/${ID}`) return Response.json(DATASET);
    if (path === `/api/datasets/${ID}/versions/1`) return Response.json(VERSION);
    if (path === `/api/datasets/${ID}/versions`) return Response.json(VERSIONS);
    if (path === `/api/datasets/${RESTRICTED_ID}`) return Response.json(RESTRICTED);
    if (path === `/api/datasets/${RESTRICTED_ID}/versions/1/download`) {
      if (downloadStatus !== 200) return Response.json({}, { status: downloadStatus });
      return Response.json({ url: "https://bucket.example/restricted/logger.csv?sig" });
    }
    return Response.json({ message: "not found" }, { status: 404 });
  });
}

function renderDataset(version?: number, id = ID) {
  return render(
    <MemoryRouter initialEntries={[`/datasets/${id}`]}>
      <Dataset id={id} version={version} />
    </MemoryRouter>,
  );
}

/** The Files list's item whose title is `title`. */
function itemOf(files: HTMLElement, title: string): HTMLElement {
  const item = [...files.querySelectorAll(":scope > li")].find(
    (li) => li.querySelector(".file-title")?.textContent === title,
  );
  if (!item) throw new Error(`no file item titled ${title}`);
  return item as HTMLElement;
}

async function filesList(): Promise<HTMLElement> {
  await screen.findByRole("heading", { level: 1, name: MANIFEST.title ?? "" });
  return screen.getByRole("list", { name: "Files" });
}

const LOGGER = /^Download Logger readings \(\d/;

beforeEach(() => {
  fetchMock = apiAnswers();
  vi.stubGlobal("fetch", fetchMock);
  sessionStorage.clear();
  downloadStatus = 200;
  vi.mocked(apiToken).mockReturnValue(null);
  vi.mocked(signIn).mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

test("every resource is a card with its kind, size and one download button", async () => {
  renderDataset();
  const files = await filesList();

  for (const resource of MANIFEST.resources ?? []) {
    const item = itemOf(files, resource.title ?? resource.name);
    expect(item.className).toContain("file");
    expect(item.textContent).toContain(resource["archive:kind"] ?? "");
  }
  const logger = within(files).getByRole("link", { name: LOGGER });
  expect(logger.getAttribute("href")).toBe(`/data/${ID}/1/data/logger.csv`);
  expect(logger.className).toContain("button");
  expect(logger.textContent).toContain("3.4 kB");
  const sites = itemOf(files, "Sites");
  expect(within(sites).getByText("Files in this set (4)").closest("details")).not.toBeNull();
  expect(
    within(sites).getByRole("link", { name: /^Download data\/sites\/sites.dbf/ }),
  ).toBeDefined();
  const linked = within(files).getByRole("link", { name: "Open link Discharge" });
  expect(linked.getAttribute("href")).toBe("https://example.org/stream-temperature/discharge.csv");
});

test("Download all and a multi-file row's Download fetch the version's zips", async () => {
  renderDataset();
  const files = await filesList();

  const all = within(screen.getByTestId("summary-strip")).getByRole("link", {
    name: /^Download all/,
  });
  expect(all.getAttribute("href")).toBe(`/data/${ID}/1/_zips/all/package.zip`);
  const sites = itemOf(files, "Sites");
  const whole = within(sites).getByRole("link", { name: /^Download Sites/ });
  expect(whole.getAttribute("href")).toBe(`/data/${ID}/1/_zips/sites.zip`);
  expect(whole.textContent).toContain("zip");
  expect(within(sites).getByText("Files in this set (4)").closest("details")).not.toBeNull();
  const logger = within(files).getByRole("link", { name: LOGGER });
  expect(logger.getAttribute("href")).toBe(`/data/${ID}/1/data/logger.csv`);
});

test("signed in on a restricted page, Download all asks the API for the package zip", async () => {
  vi.mocked(apiToken).mockReturnValue("TOKEN");
  renderDataset(undefined, RESTRICTED_ID);
  await filesList();

  fireEvent.click(
    within(screen.getByTestId("summary-strip")).getByRole("button", { name: /^Download all/ }),
  );

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  const [url] = fetchMock.mock.calls[2] as [string, RequestInit];
  expect(url).toBe(
    `/api/datasets/${RESTRICTED_ID}/versions/1/download?path=_zips%2Fall%2Fpackage.zip`,
  );
});

test("the page leads with the meta line, then the summary strip, files, columns and about", async () => {
  renderDataset();
  await filesList();

  const meta = screen.getByTestId("meta");
  for (const text of ["Ada Invented", "Version 1", "CC BY 4.0"]) {
    expect(meta.textContent).toContain(text);
  }
  const summary = screen.getByTestId("summary");
  expect(summary.textContent).toMatch(/12 files · 50\.\d kB/);
  const order = ["Files", "Columns", "About"].map((name) =>
    screen.getByRole("heading", { level: 2, name }),
  );
  expect(
    order[0]!.compareDocumentPosition(order[1]!) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(
    order[1]!.compareDocumentPosition(order[2]!) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
});

test("the citation is the README's with the versioned URL, and Copy inside its box writes it", async () => {
  const writeText = vi.fn(async () => {});
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  renderDataset();
  await filesList();

  const readme = readFileSync(join(SAMPLE, "README.md"), "utf-8").split("\n");
  const expected = `${readme[readme.indexOf("## Citation") + 2]} ${location.origin}/datasets/${ID}/v1`;
  const section = screen.getByRole("region", { name: "Cite this dataset" });
  const box = within(section).getByText(expected).closest(".citation") as HTMLElement;
  fireEvent.click(within(box).getByRole("button", { name: "Copy" }));

  await waitFor(() => expect(writeText).toHaveBeenCalledWith(expected));
  expect(await within(box).findByText("Copied ✓")).toBeDefined();
});

test("About shows the facts and Methods, and the columns tidy their dictionary", async () => {
  renderDataset();
  await filesList();

  const about = screen.getByRole("region", { name: "About" });
  for (const text of ["Ada Invented", "CC BY 4.0", "stream temperature", "2024-06-01 to ongoing"]) {
    expect(about.textContent).toContain(text);
  }
  expect(within(about).getByText("Methods")).toBeDefined();
  expect(about.textContent).toContain("Hourly loggers with field checks");

  const logger = screen.getByRole("table", { name: "Columns of Logger readings" });
  expect(logger.closest("details")?.open).toBe(true);
  expect(logger.closest("details")?.querySelector("summary")?.textContent).toContain("9 columns");
  const row = (name: string) => within(logger).getByText(name).closest("tr") as HTMLElement;
  expect(row("battery_v").textContent).toContain("No description");
  expect(row("depth_cm").textContent).toContain("No description");
  expect(row("qc_flag").textContent).toContain("No code list");
  const codes = within(row("condition")).getByRole("link", { name: "condition-codes" });
  const target = document.getElementById(codes.getAttribute("href")?.slice(1) ?? "");
  expect(target?.textContent).toContain("Logger condition codes");
});

test("spatial coverage shows its description, then the box on an outline, then the numbers", async () => {
  renderDataset();
  await filesList();

  const about = screen.getByRole("region", { name: "About" });
  const map = within(about).getByRole("img", { name: /area the data covers/ });
  expect(map.tagName.toLowerCase()).toBe("svg");
  const text = about.textContent ?? "";
  expect(text.indexOf("Three invented sites")).toBeLessThan(text.indexOf("West -72.74"));
});

test("the versions list marks the version the citation points at", async () => {
  renderDataset(1);

  const versions = await screen.findByRole("region", { name: "Versions" });
  const items = within(versions).getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(items[0]?.textContent).toContain("cited above");
  expect(items[1]?.textContent).not.toContain("cited above");
  expect(within(items[1]!).getByRole("link").getAttribute("href")).toBe(`/datasets/${ID}/v2`);
});

test("the versioned route shows a note linking to the newer version", async () => {
  renderDataset(1);

  const note = await screen.findByText(/A newer version of this dataset exists/);
  expect(within(note).getByRole("link").getAttribute("href")).toBe(`/datasets/${ID}/v2`);
  expect(screen.getByTestId("meta").textContent).toContain("Published 2024-07-01");
});

test("on the versioned route, an open prefix with no archive:access gives a plain /data link", async () => {
  const unsaid = { ...MANIFEST };
  delete unsaid["archive:access"];
  fetchMock.mockImplementation(async (url: string) => {
    const path = new URL(url, "https://site").pathname;
    if (path === `/api/datasets/${ID}/versions/1`) {
      return Response.json({ ...VERSION, manifest: unsaid });
    }
    if (path === `/api/datasets/${ID}/versions`) return Response.json(VERSIONS);
    return Response.json({ message: "not found" }, { status: 404 });
  });
  renderDataset(1);
  const files = await filesList();

  const logger = within(files).getByRole("link", { name: LOGGER });
  expect(logger.getAttribute("href")).toBe(`/data/${ID}/1/data/logger.csv`);
});

test("after a download the usage question opens as a modal dialog, outside the page, and sends the answers", async () => {
  renderDataset();
  const files = await filesList();
  expect(screen.queryByRole("dialog", { name: /how will you use this data/ })).toBeNull();

  fireEvent.click(within(files).getByRole("link", { name: LOGGER }));
  const panel = screen.getByRole("dialog", { name: /how will you use this data/ });
  // Opened modally, so it overlays the page instead of pushing the files down.
  expect(panel.tagName).toBe("DIALOG");
  expect(panel.hasAttribute("open")).toBe(true);
  expect(files.contains(panel)).toBe(false);
  expect(within(panel).getByText(/Your download has started/)).toBeDefined();
  fireEvent.change(within(panel).getByLabelText("Kind of organisation"), {
    target: { value: "university" },
  });
  fireEvent.change(within(panel).getByLabelText("Purpose"), { target: { value: "teaching" } });
  fireEvent.change(within(panel).getByLabelText(/^Note/), { target: { value: "A class" } });
  fireEvent.click(within(panel).getByRole("button", { name: "Send" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  const [url, init] = fetchMock.mock.calls[2] as [string, RequestInit];
  expect(url).toBe(`/api/datasets/${ID}/usage`);
  expect(init.method).toBe("POST");
  expect(JSON.parse(String(init.body))).toEqual({
    organisation: "university",
    purpose: "teaching",
    note: "A class",
  });
  expect(await screen.findByText("Thanks, your answers were sent anonymously.")).toBeDefined();
});

test("after No thanks the usage panel stays gone for the visit", async () => {
  renderDataset();
  const files = await filesList();
  const download = within(files).getByRole("link", { name: LOGGER });

  fireEvent.click(download);
  fireEvent.click(screen.getByRole("button", { name: "No thanks" }));
  expect(screen.queryByRole("dialog", { name: /how will you use this data/ })).toBeNull();
  fireEvent.click(download);

  expect(screen.queryByRole("dialog", { name: /how will you use this data/ })).toBeNull();
  cleanup();
  renderDataset();
  fireEvent.click(within(await filesList()).getByRole("link", { name: LOGGER }));
  expect(screen.queryByRole("dialog", { name: /how will you use this data/ })).toBeNull();
});

test("a restricted page explains access, names the contact and offers one Sign in", async () => {
  renderDataset(undefined, RESTRICTED_ID);
  const files = await filesList();

  const banner = screen.getByRole("region", { name: "Restricted" });
  expect(banner.textContent).toContain("invited accounts");
  expect(within(banner).getByRole("link", { name: "archive-admin@example.org" })).toBeDefined();
  const signIns = screen.getAllByRole("button", { name: /sign in/i });
  expect(signIns).toHaveLength(1);
  expect(within(itemOf(files, "Logger readings")).getByText("Sign in above")).toBeDefined();
  expect(within(files).queryByRole("link", { name: LOGGER })).toBeNull();

  fireEvent.click(signIns[0]!);
  expect(signIn).toHaveBeenCalledWith(`/datasets/${RESTRICTED_ID}`);
});

test("signed in, a restricted download asks the API for its link with the access token", async () => {
  vi.mocked(apiToken).mockReturnValue("TOKEN");
  renderDataset(undefined, RESTRICTED_ID);
  const files = await filesList();

  expect(screen.getByRole("region", { name: "Restricted" }).textContent).toContain(
    "You're signed in",
  );
  fireEvent.click(within(files).getByRole("button", { name: LOGGER }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  const [url, init] = fetchMock.mock.calls[2] as [string, RequestInit];
  expect(url).toBe(`/api/datasets/${RESTRICTED_ID}/versions/1/download?path=data%2Flogger.csv`);
  expect(new Headers(init.headers).get("Authorization")).toBe("Bearer TOKEN");
  expect(await screen.findByRole("dialog", { name: /how will you use this data/ })).toBeDefined();
});

test("a 401 asks the reader to sign in again", async () => {
  vi.mocked(apiToken).mockReturnValue("TOKEN");
  downloadStatus = 401;
  renderDataset(undefined, RESTRICTED_ID);
  const files = await filesList();

  fireEvent.click(within(files).getByRole("button", { name: LOGGER }));

  expect(await within(files).findByText("Your sign-in has expired.")).toBeDefined();
  fireEvent.click(within(files).getByRole("button", { name: "Sign in again Logger readings" }));
  expect(signIn).toHaveBeenCalledWith(`/datasets/${RESTRICTED_ID}`);
});

test("a 403 says the file isn't available to this account", async () => {
  vi.mocked(apiToken).mockReturnValue("TOKEN");
  downloadStatus = 403;
  renderDataset(undefined, RESTRICTED_ID);
  const files = await filesList();

  fireEvent.click(within(files).getByRole("button", { name: LOGGER }));

  expect(
    await within(files).findByText("This file isn't available to this account."),
  ).toBeDefined();
});

test("an unreachable API keeps an h1 and offers Try again, search and the current page", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  renderDataset(1);

  expect(
    await screen.findByRole("heading", { level: 1, name: "Dataset unavailable" }),
  ).toBeDefined();
  expect(screen.getByRole("link", { name: "Search the archive" }).getAttribute("href")).toBe("/");
  expect(screen.getByRole("link", { name: /current version/ }).getAttribute("href")).toBe(
    `/datasets/${ID}`,
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(
    await screen.findByRole("heading", { level: 1, name: MANIFEST.title ?? "" }),
  ).toBeDefined();
});

test("a version that isn't there links to the current one", async () => {
  renderDataset(9);

  expect(await screen.findByRole("heading", { level: 1, name: "Version not found" })).toBeDefined();
  expect(screen.getByRole("link", { name: /current version/ }).getAttribute("href")).toBe(
    `/datasets/${ID}`,
  );
});

// 5xx is ApiUnreachable already; any other refusal (429 here) isn't a missing version either.
test("a refusal other than 404 on a versioned link offers Try again, not Version not found", async () => {
  const answers = apiAnswers();
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    new URL(url, "https://site").pathname === `/api/datasets/${ID}/versions/1`
      ? Response.json({ message: "slow down" }, { status: 429 })
      : answers(url, init),
  );
  renderDataset(1);

  expect(
    await screen.findByRole("heading", { level: 1, name: "Dataset unavailable" }),
  ).toBeDefined();
  expect(screen.queryByText("Version not found")).toBeNull();
  fetchMock.mockImplementation(answers);
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(
    await screen.findByRole("heading", { level: 1, name: MANIFEST.title ?? "" }),
  ).toBeDefined();
});

test("a refusal other than 404 on a dataset reads as unavailable, not as no such dataset", async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ message: "slow down" }, { status: 429 }));
  renderDataset();

  expect(
    await screen.findByRole("heading", { level: 1, name: "Dataset unavailable" }),
  ).toBeDefined();
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

test.each([ID, RESTRICTED_ID])("an axe check of %s finds no violations", async (id) => {
  const { container } = renderDataset(undefined, id);
  const files = await filesList();
  if (id === ID) fireEvent.click(within(files).getByRole("link", { name: LOGGER }));

  const results = await axe.run(container);
  expect(results.violations).toEqual([]);
});

test("mounted into an empty #app, reaching a dataset page doesn't throw or blank the page", async () => {
  document.body.innerHTML = '<div id="app"></div>';
  history.pushState({}, "", `/datasets/${ID}`);
  const app = document.getElementById("app") as HTMLElement;
  const errors: unknown[] = [];
  const onError = (event: ErrorEvent) => errors.push(event.error);
  window.addEventListener("error", onError);

  let root: Root | undefined;
  act(() => {
    root = mount(app);
  });

  await waitFor(() => expect(app.querySelector("h1")?.textContent).toBe(MANIFEST.title ?? ""));
  window.removeEventListener("error", onError);
  expect(errors).toEqual([]);
  act(() => root?.unmount());
});
