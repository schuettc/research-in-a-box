import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link, NavLink, Route, Routes, useLocation, useParams } from "react-router";
import { addPasskey, signedInEmail, signIn, signOut, subscribe } from "./auth";
import { NavigatedContext, PageHeading, useTitle } from "./page";
import { About } from "./routes/About";
import { Callback } from "./routes/Callback";
import { Dataset } from "./routes/Dataset";
import { Search } from "./routes/Search";
import { BRAND, PUBLISHER } from "./site";

function NotFound() {
  useTitle("Not found");
  return (
    <>
      <PageHeading>Page not found</PageHeading>
      <p>
        There's nothing at this address. <Link to="/">Search the archive</Link>.
      </p>
    </>
  );
}

/** `/datasets/<id>/v<n>`: React Router matches whole segments, so the `v` is read here. */
function VersionedDataset() {
  const { id = "", version = "" } = useParams();
  const match = /^v([1-9]\d*)$/.exec(version);
  if (!match) return <NotFound />;
  return <Dataset id={id} version={Number(match[1])} />;
}

function CurrentDataset() {
  const { id = "" } = useParams();
  return <Dataset id={id} />;
}

/**
 * The header's account slot, always in the same place: Sign in when no one is signed in, else
 * one Account button whose menu names the reader and offers Add a passkey and Sign out.
 */
function Account() {
  const email = useSyncExternalStore(subscribe, signedInEmail);
  const { pathname, search } = useLocation();
  const [open, setOpen] = useState(false);
  const slot = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const here = `${pathname}${search}`;

  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!slot.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  if (!email) {
    return (
      <div className="account">
        <button type="button" className="account-button" onClick={() => void signIn(here)}>
          Sign in
        </button>
      </div>
    );
  }

  function close() {
    setOpen(false);
    trigger.current?.focus();
  }

  return (
    <div className="account" ref={slot}>
      <button
        ref={trigger}
        type="button"
        className="account-button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="account-menu"
        onClick={() => setOpen(!open)}
      >
        Account <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div
          id="account-menu"
          className="account-menu"
          role="menu"
          aria-label="Account"
          onKeyDown={(event) => {
            if (event.key === "Escape") close();
          }}
        >
          <p className="account-who">
            Signed in as <strong>{email}</strong>
          </p>
          <button
            type="button"
            role="menuitem"
            autoFocus
            onClick={() => {
              setOpen(false);
              void addPasskey(here);
            }}
          >
            Add a passkey
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              void signOut();
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function Masthead() {
  return (
    <header className="masthead">
      <div className="inner">
        <Link className="mark" to="/">
          {BRAND.logo && <img src={BRAND.logo} alt="" width="44" height="44" />}
          <span className="name">{BRAND.name}</span>
        </Link>
        <nav aria-label="Main">
          <NavLink to="/" end>
            Browse
          </NavLink>
          <NavLink to="/about">About the archive</NavLink>
        </nav>
        <Account />
      </div>
    </header>
  );
}

export function AppRoutes() {
  // Focus moves to each new page's h1, but not on the page the reader arrived at.
  const { pathname } = useLocation();
  const [seen, setSeen] = useState({ path: pathname, moved: false });
  if (seen.path !== pathname) setSeen({ path: pathname, moved: true });
  const navigated = seen.moved || seen.path !== pathname;

  return (
    <NavigatedContext value={navigated}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Masthead />
      <main id="main" tabIndex={-1}>
        <Routes>
          <Route path="/" element={<Search />} />
          <Route path="/about" element={<About />} />
          <Route path="/datasets/:id" element={<CurrentDataset />} />
          <Route path="/datasets/:id/:version" element={<VersionedDataset />} />
          <Route path="/auth/callback" element={<Callback />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="footer">
        <div className="inner">
          {PUBLISHER} · Data are shared under the licence shown on each dataset.
          {BRAND.contact && (
            <>
              {" "}
              Contact <a href={`mailto:${BRAND.contact}`}>{BRAND.contact}</a>.
            </>
          )}
        </div>
      </footer>
    </NavigatedContext>
  );
}
