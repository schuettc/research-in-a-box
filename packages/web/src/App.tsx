import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { Link, NavLink, Route, Routes, useLocation, useParams } from "react-router";
import { addPasskey, groups, signedInEmail, signIn, signOut, subscribe } from "./auth";
import { NavigatedContext, PageHeading, useTitle } from "./page";
import { About } from "./routes/About";
import { Callback } from "./routes/Callback";
import { Dataset } from "./routes/Dataset";
import { MySubmissions } from "./routes/MySubmissions";
import { Review } from "./routes/Review";
import { ReviewQueue } from "./routes/ReviewQueue";
import { Search } from "./routes/Search";
import { Settings } from "./routes/Settings";
import { Submission } from "./routes/Submission";
import { Submit } from "./routes/Submit";
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

function SubmissionRoute() {
  const { id = "" } = useParams();
  return <Submission key={id} id={id} />;
}

function ReviewRoute() {
  const { id = "" } = useParams();
  return <Review key={id} id={id} />;
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

type Role = "contributor" | "curator" | "admin";

/** The signed-in areas, in the order the nav lists them, each with the group it needs. */
const AREAS: { role: Role; to: string; label: string }[] = [
  { role: "contributor", to: "/submit", label: "Submit" },
  { role: "curator", to: "/review", label: "Review" },
  { role: "admin", to: "/settings", label: "Settings" },
];

/**
 * The nav: Browse and About in their own slot, then the areas the reader's groups allow. The
 * nav keeps one width whatever it lists, so its left edge, its first links and the Account
 * button beside it never move when areas appear.
 */
function MainNav() {
  const email = useSyncExternalStore(subscribe, signedInEmail);
  const mine = useSyncExternalStore(subscribe, groups);
  const areas = email ? AREAS.filter((area) => mine.includes(area.role)) : [];
  return (
    <nav aria-label="Main" className="nav">
      <div className="nav-public">
        <NavLink to="/" end>
          Browse
        </NavLink>
        <NavLink to="/about">About the archive</NavLink>
      </div>
      <div className="nav-areas">
        {areas.map((area) => (
          <NavLink key={area.to} to={area.to}>
            {area.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

/** What an area's page says when the reader can't use it: its heading, then why. */
function Gate({
  heading,
  title,
  role,
  email,
}: {
  heading: string;
  title: string;
  role: Role;
  email: string | null;
}) {
  useTitle(title);
  const { pathname, search } = useLocation();
  return (
    <div className="prose">
      <PageHeading>{heading}</PageHeading>
      {email ? (
        <p className="note">
          This page needs the {role} role, and your account ({email}) doesn't have it.{" "}
          {BRAND.contact ? (
            <>
              Ask the archive's admin at <a href={`mailto:${BRAND.contact}`}>{BRAND.contact}</a> to
              add it.
            </>
          ) : (
            "Ask the archive's admin to add it."
          )}
        </p>
      ) : (
        <>
          <p>Sign in to use this page.</p>
          <p className="actions">
            <button
              type="button"
              className="primary"
              onClick={() => void signIn(`${pathname}${search}`)}
            >
              Sign in
            </button>
          </p>
        </>
      )}
    </div>
  );
}

/** A signed-in area: its page for a reader in `role`, else its heading with Sign in or why not. */
function Area({
  role,
  heading,
  title,
  children,
}: {
  role: Role;
  heading: string;
  title: string;
  children: ReactNode;
}) {
  const email = useSyncExternalStore(subscribe, signedInEmail);
  const mine = useSyncExternalStore(subscribe, groups);
  if (!email || !mine.includes(role)) {
    return <Gate heading={heading} title={title} role={role} email={email} />;
  }
  return children;
}

function Masthead() {
  return (
    <header className="masthead">
      <div className="inner">
        <Link className="mark" to="/">
          {BRAND.logo && <img src={BRAND.logo} alt="" width="44" height="44" />}
          <span className="name">{BRAND.name}</span>
        </Link>
        <MainNav />
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
          <Route
            path="/submit"
            element={
              <Area role="contributor" heading="Submit a package" title="Submit">
                <Submit />
              </Area>
            }
          />
          <Route
            path="/submissions"
            element={
              <Area role="contributor" heading="My submissions" title="My submissions">
                <MySubmissions />
              </Area>
            }
          />
          <Route
            path="/submissions/:id"
            element={
              <Area role="contributor" heading="Submission" title="Submission">
                <SubmissionRoute />
              </Area>
            }
          />
          <Route
            path="/review"
            element={
              <Area role="curator" heading="Review queue" title="Review queue">
                <ReviewQueue />
              </Area>
            }
          />
          <Route
            path="/review/:id"
            element={
              <Area role="curator" heading="Review" title="Review">
                <ReviewRoute />
              </Area>
            }
          />
          <Route
            path="/settings"
            element={
              <Area role="admin" heading="Settings" title="Settings">
                <Settings />
              </Area>
            }
          />
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
