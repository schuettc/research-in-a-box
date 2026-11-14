import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

test("checking a facet adds a repeated parameter and keeps the others", async () => {
  renderAt("/?q=stream&access=open&page=2");
  fireEvent.click(await screen.findByRole("checkbox", { name: "restricted (2)" }));

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  const sent = requests()[1];
  expect(sent?.get("q")).toBe("stream");
  expect(sent?.getAll("access")).toEqual(["open", "restricted"]);
  expect(sent?.get("page")).toBe("1");
  expect(sent?.get("size")).toBe("20");
});

test("while the next search loads, the last answer stays and the unchecked facet keeps focus", async () => {
  renderAt("/?access=open");
  const box = await screen.findByRole("checkbox", { name: "open (1)" });
  fetchMock.mockImplementation(() => new Promise(() => {}));
  box.focus();
  fireEvent.click(box);

  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(screen.getByText("Searching…").getAttribute("aria-live")).toBe("polite");
  const after = screen.getByRole("checkbox", { name: "open (1)" }) as HTMLInputElement;
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
  expect((screen.getByRole("checkbox", { name: "csv (1)" }) as HTMLInputElement).checked).toBe(
    true,
  );
});

test("a result card shows the row's own fields", async () => {
  renderAt("/");

  const link = await screen.findByRole("link", { name: ANSWER.rows[0]?.title });
  expect(link.getAttribute("href")).toBe("/datasets/stream-temperature-sample");
  const card = link.closest("article");
  for (const text of ["open", "CC-BY-4.0", "csv", "shp", "2024-06-01 to ongoing", "Ada Invented"]) {
    expect(card?.textContent).toContain(text);
  }
});

test("no results says so, and Clear filters clears the search", async () => {
  answer(EMPTY);
  renderAt("/?q=nothing&access=open");

  expect(await screen.findByText("No datasets match this search.")).toBeDefined();
  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));

  await waitFor(() => expect(screen.getByTestId("where").textContent).toBe(""));
});

test("an unreachable API shows one line and Try again", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  renderAt("/");

  expect((await screen.findByRole("alert")).textContent).toBe("Search is unavailable right now.");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(await screen.findByRole("link", { name: ANSWER.rows[0]?.title })).toBeDefined();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("an axe check of the page finds no violations", async () => {
  const { container } = renderAt("/");
  await screen.findByRole("link", { name: ANSWER.rows[0]?.title });

  const results = await axe.run(container);
  expect(results.violations).toEqual([]);
});
