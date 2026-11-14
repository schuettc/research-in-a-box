import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { search, type CatalogRow, type SearchAnswer } from "../api";
import {
  accessClass,
  accessFacetLabel,
  accessLabel,
  formatLabel,
  formatSize,
  kindsOf,
  licenceLabel,
} from "../labels";
import { PageHeading, useTitle } from "../page";
import { BRAND } from "../site";

const FACETS = [
  ["access", "Access", accessFacetLabel],
  ["license", "Licence", licenceLabel],
  ["format", "Format", formatLabel],
  ["project", "Project", (value: string) => value],
] as const;
const PAGE_SIZE = 20;
const DEBOUNCE_MS = 300;
const YEAR = /^\d{4}$/;

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

/** How many filters are on: each checked facet value, and each year. */
function activeFilters(params: URLSearchParams): number {
  const facets = FACETS.reduce((n, [facet]) => n + params.getAll(facet).length, 0);
  return facets + (params.get("from") ? 1 : 0) + (params.get("to") ? 1 : 0);
}

type Loaded = { query: string; attempt: number } & (
  { answer: SearchAnswer } | { unavailable: true }
);

function yearsOf(row: CatalogRow): string | null {
  if (!row.start) return null;
  const end = row.ongoing ? "ongoing" : (row.end?.slice(0, 4) ?? "unknown");
  return `${row.start.slice(0, 4)} – ${end}`;
}

const capitalised = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

/** One result: what a reader needs to choose between datasets, access first. */
function Entry({ row }: { row: CatalogRow }) {
  const who = row.creators?.length ? row.creators.join(", ") : row.project;
  const by = [who, yearsOf(row)].filter(Boolean).join(" · ");
  const kinds = kindsOf(row.formats ?? []);
  const meta: [string, string][] = [];
  if (row.licenses?.length) meta.push(["Licence", row.licenses.map(licenceLabel).join(", ")]);
  if (kinds.length) meta.push(["Files", capitalised(kinds.join(", "))]);
  if (typeof row.bytes === "number") meta.push(["Size", formatSize(row.bytes)]);
  if (row.published) meta.push(["Published", row.published.slice(0, 10)]);
  return (
    <article className="entry">
      <span className={accessClass(row.access)}>{accessLabel(row.access)}</span>
      <h2>
        <Link to={`/datasets/${encodeURIComponent(row.id)}`}>{row.title}</Link>
      </h2>
      {by && <p className="by">{by}</p>}
      {row.description && <p className="clamp">{row.description}</p>}
      {meta.length > 0 && (
        <p className="meta">
          {meta.map(([term, value]) => (
            <span key={term}>
              <b>{term}</b> {value}
            </span>
          ))}
        </p>
      )}
    </article>
  );
}

/** A year box: follows the URL, and writes a whole year (or nothing) to it after a pause. */
function useYear(name: "from" | "to") {
  const [params, setParams] = useSearchParams();
  const year = params.get(name) ?? "";
  const [text, setText] = useState(year);
  const [shown, setShown] = useState(year);
  if (year !== shown) {
    setShown(year);
    setText(year);
  }
  useEffect(() => {
    if (text === year || (text !== "" && !YEAR.test(text))) return;
    const timer = setTimeout(() => {
      setParams((previous) => {
        const next = new URLSearchParams(previous);
        if (text) next.set(name, text);
        else next.delete(name);
        next.delete("page");
        return next;
      });
    }, DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text, year, name, setParams]);
  return [text, setText] as const;
}

function yearsHint(from: string, to: string): string {
  if ([from, to].some((year) => year !== "" && !YEAR.test(year))) {
    return "Enter a four-digit year, such as 2019.";
  }
  if (YEAR.test(from) && YEAR.test(to) && from > to) return "The From year is after the To year.";
  return "";
}

export function Search() {
  useTitle("Search");
  const [params, setParams] = useSearchParams();
  const box = useRef<HTMLInputElement>(null);
  const q = params.get("q") ?? "";
  const query = apiQuery(params);
  const page = pageOf(params);
  const active = activeFilters(params);
  const everything = !q && active === 0;

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

  const [fromText, setFromText] = useYear("from");
  const [toText, setToText] = useYear("to");
  const hint = yearsHint(fromText, toText);
  const [filtersOpen, setFiltersOpen] = useState(false);

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

  // The last answer stays on screen while the next one loads, so focus isn't lost.
  const answer = loaded && "answer" in loaded ? loaded.answer : null;

  // The archive's own facet values, so a search with no results still shows what there is.
  const [archive, setArchive] = useState<SearchAnswer["facets"] | null>(null);
  const answerIsEverything = result !== null && "answer" in result && everything;
  if (answerIsEverything && archive === null) setArchive(result.answer.facets);
  const needArchive = answer?.total === 0 && archive === null;
  useEffect(() => {
    if (!needArchive) return;
    let current = true;
    search(new URLSearchParams({ page: "1", size: "1" })).then(
      (all) => current && setArchive(all.facets),
      () => {},
    );
    return () => {
      current = false;
    };
  }, [needArchive]);

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

  function goTo(nextPage: number) {
    update((next) => next.set("page", String(nextPage)));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    update((next) => {
      if (text) next.set("q", text);
      else next.delete("q");
      next.delete("page");
    });
  }

  /** Clear the filters, keeping the words searched for. */
  function clearFilters() {
    setParams(text ? new URLSearchParams({ q: text }) : new URLSearchParams());
    box.current?.focus();
  }

  function searchEverything() {
    setText("");
    setParams(new URLSearchParams());
    box.current?.focus();
  }

  const pages = answer ? Math.ceil(answer.total / PAGE_SIZE) : 0;

  return (
    <div className="search">
      <PageHeading>Search the archive</PageHeading>
      {everything && BRAND.intro && <p className="lede">{BRAND.intro}</p>}
      <form className="search-form" role="search" onSubmit={submit}>
        <label htmlFor="search-q">Search</label>
        <input
          id="search-q"
          ref={box}
          type="search"
          placeholder="Title, keyword, creator or column name"
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
        <button type="submit" className="primary">
          Search
        </button>
      </form>
      <button
        type="button"
        className="filters-toggle"
        aria-expanded={filtersOpen}
        aria-controls="filters"
        onClick={() => setFiltersOpen((open) => !open)}
      >
        Filters{active > 0 ? ` (${active} active)` : ""}
      </button>
      <div className="search-layout">
        <aside
          id="filters"
          className={`filters${filtersOpen ? " open" : ""}`}
          aria-label="Narrow the results"
        >
          {FACETS.map(([facet, label, word]) => {
            const counts = answer?.facets[facet] ?? {};
            const checked = params.getAll(facet);
            const fromArchive = answer?.total === 0 ? Object.keys(archive?.[facet] ?? {}) : [];
            const values = [...new Set([...fromArchive, ...Object.keys(counts), ...checked])];
            if (values.length === 0) return null;
            return (
              <fieldset key={facet} className="facet-group">
                <legend>{label}</legend>
                {values.map((value) => {
                  const count = counts[value] ?? 0;
                  return (
                    <label key={value} className={`facet${count === 0 ? " none" : ""}`}>
                      <input
                        type="checkbox"
                        checked={checked.includes(value)}
                        onChange={() => toggle(facet, value)}
                      />
                      <span>{word(value)}</span>{" "}
                      <span className="count" aria-hidden="true">
                        {count}
                      </span>{" "}
                      <span className="visually-hidden">({count})</span>
                    </label>
                  );
                })}
              </fieldset>
            );
          })}
          <fieldset className="facet-group">
            <legend>Years</legend>
            <div className="year-row">
              <label>
                From
                <input
                  aria-label="From year"
                  type="text"
                  inputMode="numeric"
                  pattern="\d{4}"
                  maxLength={4}
                  placeholder="1950"
                  aria-describedby="years-hint"
                  value={fromText}
                  onChange={(event) => setFromText(event.target.value.trim())}
                />
              </label>
              <label>
                to
                <input
                  aria-label="To year"
                  type="text"
                  inputMode="numeric"
                  pattern="\d{4}"
                  maxLength={4}
                  placeholder="2026"
                  aria-describedby="years-hint"
                  value={toText}
                  onChange={(event) => setToText(event.target.value.trim())}
                />
              </label>
            </div>
            <p id="years-hint" className="hint" aria-live="polite">
              {hint}
            </p>
          </fieldset>
        </aside>
        <section className="results" aria-label="Results">
          <p className="visually-hidden" aria-live="polite">
            {result ? "" : "Searching…"}
          </p>
          {result && "unavailable" in result && (
            <>
              <p role="alert">
                Search is unavailable right now.
                {BRAND.contact && (
                  <>
                    {" "}
                    If this keeps happening, contact{" "}
                    <a href={`mailto:${BRAND.contact}`}>{BRAND.contact}</a>.
                  </>
                )}
              </p>
              <button type="button" onClick={() => setAttempt((n) => n + 1)}>
                Try again
              </button>
            </>
          )}
          {answer && answer.total === 0 && (
            <div className="none">
              <p className="results-head">
                <strong>
                  {q ? `No datasets match “${q}”.` : "No datasets match these filters."}
                </strong>
              </p>
              {q && <p className="muted">Check the spelling, or try fewer words.</p>}
              <p className="actions">
                {active > 0 && (
                  <button type="button" onClick={clearFilters}>
                    Clear filters
                  </button>
                )}
                <button type="button" onClick={searchEverything}>
                  Search everything
                </button>
              </p>
            </div>
          )}
          {answer && answer.total > 0 && (
            <>
              <p className="results-head" aria-live="polite">
                <strong>
                  {answer.total} {answer.total === 1 ? "dataset" : "datasets"}
                  {everything ? " in the archive" : ""}
                </strong>
              </p>
              {answer.rows.map((row) => (
                <Entry key={row.id} row={row} />
              ))}
              {pages > 1 && (
                <nav className="pager" aria-label="Pages">
                  <button type="button" disabled={page <= 1} onClick={() => goTo(page - 1)}>
                    Previous
                  </button>
                  <span>
                    Page {page} of {pages}
                  </span>
                  <button type="button" disabled={page >= pages} onClick={() => goTo(page + 1)}>
                    Next
                  </button>
                </nav>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
