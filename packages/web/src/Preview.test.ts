import { afterEach, expect, test, vi } from "vitest";
import { parseCsv, readHead } from "./Preview";

afterEach(() => vi.unstubAllGlobals());

test("quoted fields keep their commas, quotes and newlines", () => {
  expect(parseCsv('site,note\r\nS1,"wet, cold"\nS2,"said ""hi""\nthen left"\n')).toEqual([
    ["site", "note"],
    ["S1", "wet, cold"],
    ["S2", 'said "hi"\nthen left'],
  ]);
});

test("a file longer than the range read loses its cut last line; a whole one keeps every line", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("a,b\n1,2\n3,", { status: 206 })),
  );

  expect(await readHead("https://x/f.csv", 100_000)).toEqual([
    ["a", "b"],
    ["1", "2"],
  ]);
  expect(await readHead("https://x/f.csv", 10)).toEqual([
    ["a", "b"],
    ["1", "2"],
    ["3", ""],
  ]);
});
