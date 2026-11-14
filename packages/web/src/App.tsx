import { Link, Route, Routes, useParams } from "react-router";
import { Callback } from "./routes/Callback";
import { Dataset } from "./routes/Dataset";
import { Search } from "./routes/Search";

declare const __PUBLISHER__: string;

function NotFound() {
  return (
    <>
      <h1>Page not found</h1>
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

export function AppRoutes() {
  return (
    <>
      <header className="site-header">
        <Link to="/">{__PUBLISHER__}</Link>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Search />} />
          <Route path="/datasets/:id" element={<CurrentDataset />} />
          <Route path="/datasets/:id/:version" element={<VersionedDataset />} />
          <Route path="/auth/callback" element={<Callback />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </>
  );
}
