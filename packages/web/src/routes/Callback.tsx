import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { completeSignIn, lastReturnTo, signIn } from "../auth";
import { PageHeading, useTitle } from "../page";

/** `/auth/callback`: finish sign-in, then go back to the page the reader came from. */
export function Callback() {
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
              {returnTo.startsWith("/datasets/") ? "Back to the dataset" : "Back to search"}
            </Link>
          </p>
        </>
      ) : (
        <p role="status">One moment…</p>
      )}
    </>
  );
}
