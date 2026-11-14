import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { completeSignIn } from "../auth";
import { PageHeading, useTitle } from "../page";

/** `/auth/callback`: finish sign-in, then go back to the page the reader came from. */
export function Callback() {
  useTitle("Signing in");
  const navigate = useNavigate();
  const [failed, setFailed] = useState(false);

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
        <p role="alert">
          Sign-in didn't finish. <Link to="/">Back to search</Link>.
        </p>
      ) : (
        <p role="status">One moment…</p>
      )}
    </>
  );
}
