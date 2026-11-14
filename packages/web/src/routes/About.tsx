import { PageHeading, useTitle } from "../page";
import { BRAND } from "../site";

/** `/about`: the brand's intro and how to reach the archive. */
export function About() {
  useTitle("About");
  return (
    <div className="prose">
      <PageHeading>About the archive</PageHeading>
      <p className="lede">{BRAND.intro ?? `${BRAND.name} shares its research data here.`}</p>
      {BRAND.contact && (
        <p>
          Questions, or asking for access to a restricted dataset:{" "}
          <a href={`mailto:${BRAND.contact}`}>{BRAND.contact}</a>.
        </p>
      )}
    </div>
  );
}
