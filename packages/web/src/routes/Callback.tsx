import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { clearPasskeyReturn, completeSignIn, lastReturnTo, passkeyReturn, signIn } from "../auth";
import { PageHeading, useTitle } from "../page";

const backLabel = (to: string) =>
  to.startsWith("/datasets/") ? "Back to the dataset" : "Back to search";

/**
 * `/auth/callback`: finish sign-in, then go back to the page the reader came from. Managed login
 * also comes back here, with no code, after adding a passkey; that says so and offers Sign in,
 * which managed login's session makes one click.
 */
export function Callback() {
  const { search } = useLocation();
  const [passkey] = useState(() => passkeyReturn(search));
  return passkey === null ? <FinishSignIn /> : <PasskeyAdded returnTo={passkey} />;
}

function PasskeyAdded({ returnTo }: { returnTo: string }) {
  useTitle("Passkey added");
  useEffect(() => clearPasskeyReturn(), []);

  return (
    <>
      <PageHeading>Passkey added</PageHeading>
      <p role="status">Your passkey is saved. Sign in again to carry on.</p>
      <p className="actions">
        <button type="button" className="primary" onClick={() => void signIn(returnTo)}>
          Sign in
        </button>
        <Link className="button" to={returnTo}>
          {backLabel(returnTo)}
        </Link>
      </p>
    </>
  );
}

function FinishSignIn() {
  useTitle("Signing in");
  const navigate = useNavigate();
  const [failed, setFailed] = useState(false);
  const returnTo = lastReturnTo();

  useEffect(() => {
    completeSignIn().then(
      (returnTo) => navigate(returnTo, { replace: true }),
      () => setFailed(true),
    );
  }, [navigate]);

  return (
    <>
      <PageHeading>Signing in</PageHeading>
      {failed ? (
        <>
          <p role="alert">Sign-in didn't finish.</p>
          <p className="actions">
            <button type="button" className="primary" onClick={() => void signIn(returnTo)}>
              Try again
            </button>
            <Link className="button" to={returnTo}>
              {backLabel(returnTo)}
            </Link>
          </p>
        </>
      ) : (
        <p role="status">One moment…</p>
      )}
    </>
  );
}
