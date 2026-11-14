import { PageHeading, useTitle } from "../page";

export function Submission({ id }: { id: string }) {
  useTitle("Submission");
  return <PageHeading>Submission {id}</PageHeading>;
}
