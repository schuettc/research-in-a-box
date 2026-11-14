import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, expect, test, vi, type Mock } from "vitest";
import type { SearchAnswer } from "../api";
import { Search } from "./Search";

const ANSWER: SearchAnswer = {
  total: 1,
  rows: [
    {
      id: "stream-temperature-sample",
      version: 1,
      title: "Stream temperature at three invented sites",
      access: "open",
      description: "Hourly water temperature from loggers at three invented stream sites.",
      licenses: ["CC-BY-4.0"],
      formats: ["csv", "shp"],
      start: "2024-06-01",
      ongoing: true,
      creators: ["Ada Invented"],
    },
  ],
  facets: {
    access: { open: 1, restricted: 2 },
    license: { "CC-BY-4.0": 1 },
    format: { csv: 1, shp: 1 },
    project: {},
  },
};

const ROW = ANSWER.rows[0]!;
const EMPTY: SearchAnswer = { total: 0, rows: [], facets: {} };

let fetchMock: Mock;

function answer(body: SearchAnswer) {
  fetchMock.mockImplementation(async () => Response.json(body));
}

function Where() {
  const location = useLocation();
  return <output data-testid="where">{location.search}</output>;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<Search />} />
      </Routes>
      <Where />
    </MemoryRouter>,
  );
}

/** The query string of each request the page sent. */
function requests(): URLSearchParams[] {
  return fetchMock.mock.calls.map(([url]) => new URL(String(url), "https://site").searchParams);
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  answer(ANSWER);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("typing sends one request after the debounce", async () => {
  vi.useFakeTimers();
  renderAt("/");
  await act(() => vi.advanceTimersByTimeAsync(0));
  expect(fetchMock).toHaveBeenCalledTimes(1);

  const box = screen.getByRole("searchbox", { name: "Search" });
  for (const text of ["s", "st", "str"]) {
    fireEvent.change(box, { target: { value: text } });
    await act(() => vi.advanceTimersByTimeAsync(100));
  }
  expect(fetchMock).toHaveBeenCalledTimes(1);
  await act(() => vi.advanceTimersByTimeAsync(300));

  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(requests()[1]?.get("q")).toBe("str");
  expect(screen.getByTestId("where").textContent).toBe("?q=str");
});

test("typing a year keeps focus in the box and sends it after the debounce", async () => {
  vi.useFakeTimers();
  renderAt("/");
  await act(() => vi.advanceTimersByTimeAsync(0));

  const from = screen.getByRole("textbox", { name: "From year" });
  from.focus();
  for (const text of ["2", "20", "202", "2020"]) {
    fireEvent.change(from, { target: { value: text } });
    await act(() => vi.advanceTimersByTimeAsync(100));
  }
  await act(() => vi.advanceTimersByTimeAsync(300));

  expect(document.activeElement).toBe(from);
  expect((from as HTMLInputElement).value).toBe("2020");
  expect(requests().at(-1)?.get("from")).toBe("2020-01-01");
});

test("checking a facet adds a repeated parameter and keeps the others", async () => {
  renderAt("/?q=stream&access=open&page=2");
  fireEvent.click(await screen.findByRole("checkbox", { name: "Restricted (2)" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const sent = requests()[1];
  expect(sent?.get("q")).toBe("stream");
  expect(sent?.getAll("access")).toEqual(["open", "restricted"]);
  expect(sent?.get("page")).toBe("1");
  expect(sent?.get("size")).toBe("20");
});

test("while the next search loads, the last answer stays and the unchecked facet keeps focus", async () => {
  renderAt("/?access=open");
  const box = await screen.findByRole("checkbox", { name: "Open access (1)" });
  fetchMock.mockImplementation(() => new Promise(() => {}));
  box.focus();
  fireEvent.click(box);

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(screen.getByText("Searching…").getAttribute("aria-live")).toBe("polite");
  const after = screen.getByRole("checkbox", { name: "Open access (1)" }) as HTMLInputElement;
  expect(after.checked).toBe(false);
  expect(document.activeElement).toBe(after);
  expect(screen.getByRole("link", { name: ANSWER.rows[0]?.title })).toBeDefined();
});

test("a search URL loaded fresh sends the same request", async () => {
  renderAt("/?q=stream&license=CC-BY-4.0&format=csv&format=shp&from=2020&to=2024&page=3");

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const sent = requests()[0];
  expect(sent?.get("q")).toBe("stream");
  expect(sent?.getAll("license")).toEqual(["CC-BY-4.0"]);
  expect(sent?.getAll("format")).toEqual(["csv", "shp"]);
  expect(sent?.get("from")).toBe("2020-01-01");
  expect(sent?.get("to")).toBe("2024-12-31");
  expect(sent?.get("page")).toBe("3");
  expect((screen.getByRole("searchbox", { name: "Search" }) as HTMLInputElement).value).toBe(
    "stream",
  );
  expect(
    (screen.getByRole("checkbox", { name: "CSV (.csv) (1)" }) as HTMLInputElement).checked,
  ).toBe(true);
});

test("an entry shows the access label before the title, and no raw extension", async () => {
  answer({ ...ANSWER, rows: [{ ...ROW, bytes: 50_000, published: "2026-11-13T20:14:00Z" }] });
  renderAt("/");

  const link = await screen.findByRole("link", { name: ROW.title });
  expect(link.getAttribute("href")).toBe("/datasets/stream-temperature-sample");
  const entry = link.closest("article") as HTMLElement;
  const label = within(entry).getByText("Open");
  expect(label.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  for (const text of [
    "Ada Invented · 2024 – ongoing",
    "CC BY 4.0",
    "Tables, GIS",
    "50.0 kB",
    "2026-11-13",
  ]) {
    expect(entry.textContent).toContain(text);
  }
  expect(entry.textContent).not.toMatch(/\b(csv|shp)\b/);
});

test("a restricted entry says Restricted", async () => {
  answer({ ...ANSWER, rows: [{ ...ROW, access: "restricted" }] });
  renderAt("/");

  const link = await screen.findByRole("link", { name: ROW.title });
  expect(within(link.closest("article") as HTMLElement).getByText("Restricted")).toBeDefined();
});

test("facet labels are words, and the URL keeps the token", async () => {
  renderAt("/");

  fireEvent.click(await screen.findByRole("checkbox", { name: "Shapefile (.shp) (1)" }));
  await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("?format=shp"));
  expect(screen.getByRole("checkbox", { name: "CC BY 4.0 (1)" })).toBeDefined();
});

test("no results keeps the facets at 0, echoes the query and offers two ways out", async () => {
  fetchMock.mockImplementation(async (url: string) =>
    Response.json(new URL(url, "https://site").searchParams.get("q") ? EMPTY : ANSWER),
  );
  renderAt("/?q=nothing&access=open");

  expect(await screen.findByText("No datasets match “nothing”.")).toBeDefined();
  expect(await screen.findByRole("checkbox", { name: "Restricted (0)" })).toBeDefined();
  expect(screen.getByRole("checkbox", { name: "Open access (0)" })).toBeDefined();
  expect(screen.getByRole("checkbox", { name: "Shapefile (.shp) (0)" })).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  await waitFor(() => expect(screen.getByTestId("where").textContent).toBe("?q=nothing"));
  expect(document.activeElement).toBe(screen.getByRole("searchbox", { name: "Search" }));
  fireEvent.click(screen.getByRole("button", { name: "Search everything" }));
  await waitFor(() => expect(screen.getByTestId("where").textContent).toBe(""));
});

test("Enter searches at once", async () => {
  vi.useFakeTimers();
  renderAt("/");
  await act(() => vi.advanceTimersByTimeAsync(0));

  fireEvent.change(screen.getByRole("searchbox", { name: "Search" }), {
    target: { value: "stream" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await act(() => vi.advanceTimersByTimeAsync(0));

  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(requests()[1]?.get("q")).toBe("stream");
});

test("a three-digit year shows the hint and sends no filter", async () => {
  vi.useFakeTimers();
  renderAt("/");
  await act(() => vi.advanceTimersByTimeAsync(0));

  fireEvent.change(screen.getByRole("textbox", { name: "From year" }), {
    target: { value: "202" },
  });
  await act(() => vi.advanceTimersByTimeAsync(1000));

  expect(screen.getByText("Enter a four-digit year, such as 2019.")).toBeDefined();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("where").textContent).toBe("");
});

test("a reversed range says so", async () => {
  renderAt("/?from=2024&to=2020");

  expect(await screen.findByText("The From year is after the To year.")).toBeDefined();
});

test("one page shows no pager; more show Page 1 of n", async () => {
  renderAt("/");
  await screen.findByRole("link", { name: ROW.title });
  expect(screen.queryByRole("navigation", { name: "Pages" })).toBeNull();

  cleanup();
  answer({ ...ANSWER, total: 45 });
  renderAt("/");
  const pages = await screen.findByRole("navigation", { name: "Pages" });
  expect(pages.textContent).toContain("Page 1 of 3");
});

test("the filters collapse behind a button that counts the active ones", async () => {
  renderAt("/?access=open&from=2020");

  const toggle = await screen.findByRole("button", { name: "Filters (2 active)" });
  const filters = document.getElementById(toggle.getAttribute("aria-controls") ?? "");
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  expect(filters?.className).not.toContain("open");
  fireEvent.click(toggle);

  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  expect(filters?.className).toContain("open");
});

test("the home page opens with the archive's intro and its count", async () => {
  renderAt("/");

  expect(await screen.findByText("1 dataset in the archive")).toBeDefined();
  expect(screen.getByText(/shares the data behind its field studies/)).toBeDefined();
});

test("an unreachable API shows one line and Try again", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  renderAt("/");

  expect((await screen.findByRole("alert")).textContent).toBe(
    "Search is unavailable right now. If this keeps happening, contact archive-admin@example.org.",
  );
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(await screen.findByRole("link", { name: ANSWER.rows[0]?.title })).toBeDefined();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("an axe check finds no violations, with the filters closed and open", async () => {
  const { container } = renderAt("/?access=open");
  await screen.findByRole("link", { name: ROW.title });

  expect((await axe.run(container)).violations).toEqual([]);
  fireEvent.click(screen.getByRole("button", { name: /^Filters/ }));
  expect((await axe.run(container)).violations).toEqual([]);
});
