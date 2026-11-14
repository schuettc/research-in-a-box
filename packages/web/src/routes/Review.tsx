import { PageHeading, useTitle } from "../page";

export function Review({ id }: { id: string }) {
  useTitle("Review");
  return <PageHeading>Review {id}</PageHeading>;
}
