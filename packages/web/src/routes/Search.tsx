import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { search, type CatalogRow, type SearchAnswer } from "../api";

const FACETS = [
  ["access", "Access"],
  ["license", "Licence"],
  ["format", "Format"],
  ["project", "Project"],
] as const;
const PAGE_SIZE = 20;
const DEBOUNCE_MS = 300;

function pageOf(params: URLSearchParams): number {
  const page = Number(params.get("page"));
  return Number.isInteger(page) && page > 0 ? page : 1;
}

/** The API's query for the page's query string: years become the first and last day. */
function apiQuery(params: URLSearchParams): string {
  const query = new URLSearchParams();
  const q = params.get("q");
  if (q) query.set("q", q);
  for (const [facet] of FACETS) {
    for (const value of params.getAll(facet)) query.append(facet, value);
  }
  const from = params.get("from");
  if (from) query.set("from", `${from}-01-01`);
  const to = params.get("to");
  if (to) query.set("to", `${to}-12-31`);
  query.set("page", String(pageOf(params)));
  query.set("size", String(PAGE_SIZE));
  return query.toString();
}

type Loaded = { query: string; attempt: number } & (
  { answer: SearchAnswer } | { unavailable: true }
);

function dateRange(row: CatalogRow): string | null {
  if (!row.start) return null;
  const end = row.ongoing ? "ongoing" : (row.end ?? "an unknown end");
  return `${row.start} to ${end}`;
}

function ResultCard({ row }: { row: CatalogRow }) {
  const range = dateRange(row);
  const who = row.project ?? (row.creators?.length ? row.creators.join(", ") : null);
  return (
    <article className="result">
      <h2>
        <Link to={`/datasets/${encodeURIComponent(row.id)}`}>{row.title}</Link>
      </h2>
      {row.description && <p className="clamp">{row.description}</p>}
      <ul className="badges">
        <li>{row.access}</li>
        {row.licenses?.map((license) => (
          <li key={`license-${license}`}>{license}</li>
        ))}
        {row.formats?.map((format) => (
          <li key={`format-${format}`}>{format}</li>
        ))}
        {range && <li>{range}</li>}
        {who && <li>{who}</li>}
      </ul>
    </article>
  );
}

export function Search() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const query = apiQuery(params);
  const page = pageOf(params);

  // The box follows the URL (back button, shared link) and writes to it after a pause.
  const [text, setText] = useState(q);
  const [shownQ, setShownQ] = useState(q);
  if (q !== shownQ) {
    setShownQ(q);
    setText(q);
  }
  useEffect(() => {
    if (text === q) return;
    const timer = setTimeout(() => {
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          if (text) next.set("q", text);
          else next.delete("q");
          next.delete("page");
          return next;
        },
        { replace: true },
      );
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text, q, setParams]);

  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  useEffect(() => {
    let current = true;
    search(new URLSearchParams(query)).then(
      (answer) => current && setLoaded({ query, attempt, answer }),
      () => current && setLoaded({ query, attempt, unavailable: true }),
    );
    return () => {
      current = false;
    };
  }, [query, attempt]);
  const result = loaded && loaded.query === query && loaded.attempt === attempt ? loaded : null;

  function update(change: (next: URLSearchParams) => void) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      change(next);
      return next;
    });
  }

  function toggle(facet: string, value: string) {
    update((next) => {
      const values = next.getAll(facet);
      next.delete(facet);
      const kept = values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
      for (const v of kept) next.append(facet, v);
      next.delete("page");
    });
  }

  function setYear(name: "from" | "to", value: string) {
    if (value !== "" && !/^\d{4}$/.test(value)) return;
    update((next) => {
      if (value) next.set(name, value);
      else next.delete(name);
      next.delete("page");
    });
  }

  function goTo(nextPage: number) {
    update((next) => next.set("page", String(nextPage)));
  }

  function clearFilters() {
    setText("");
    setParams(new URLSearchParams());
  }

  // The last answer stays on screen while the next one loads, so focus isn't lost.
  const answer = loaded && "answer" in loaded ? loaded.answer : null;

  return (
    <div className="search">
      <h1>Search the archive</h1>
      <form role="search" onSubmit={(event) => event.preventDefault()}>
        <label htmlFor="search-q">Search</label>
        <input
          id="search-q"
          type="search"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </form>
      <div className="search-layout">
        <aside className="filters">
          {FACETS.map(([facet, label]) => {
            const counts = answer?.facets[facet] ?? {};
            const checked = params.getAll(facet);
            const values = [...new Set([...Object.keys(counts), ...checked])];
            if (values.length === 0) return null;
            return (
              <fieldset key={facet}>
                <legend>{label}</legend>
                {values.map((value) => (
                  <label key={value} className="facet">
                    <input
                      type="checkbox"
                      checked={checked.includes(value)}
                      onChange={() => toggle(facet, value)}
                    />
                    {value} ({counts[value] ?? 0})
                  </label>
                ))}
              </fieldset>
            );
          })}
          <fieldset>
            <legend>Years</legend>
            <label className="year">
              From year
              <input
                type="number"
                inputMode="numeric"
                defaultValue={params.get("from") ?? ""}
                key={`from-${params.get("from") ?? ""}`}
                onChange={(event) => setYear("from", event.target.value)}
              />
            </label>
            <label className="year">
              To year
              <input
                type="number"
                inputMode="numeric"
                defaultValue={params.get("to") ?? ""}
                key={`to-${params.get("to") ?? ""}`}
                onChange={(event) => setYear("to", event.target.value)}
              />
            </label>
          </fieldset>
        </aside>
        <section className="results" aria-label="Results">
          <p aria-live="polite">{result ? "" : "Searching…"}</p>
          {result && "unavailable" in result && (
            <>
              <p role="alert">Search is unavailable right now.</p>
              <button type="button" onClick={() => setAttempt((n) => n + 1)}>
                Try again
              </button>
            </>
          )}
          {answer && answer.total === 0 && (
            <>
              <p>No datasets match this search.</p>
              <button type="button" onClick={clearFilters}>
                Clear filters
              </button>
            </>
          )}
          {answer && answer.total > 0 && (
            <>
              <p aria-live="polite">
                {answer.total} {answer.total === 1 ? "dataset" : "datasets"}
              </p>
              {answer.rows.map((row) => (
                <ResultCard key={row.id} row={row} />
              ))}
              <nav className="pages" aria-label="Pages">
                <button type="button" disabled={page <= 1} onClick={() => goTo(page - 1)}>
                  Previous
                </button>
                <button
                  type="button"
                  disabled={page * PAGE_SIZE >= answer.total}
                  onClick={() => goTo(page + 1)}
                >
                  Next
                </button>
              </nav>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
