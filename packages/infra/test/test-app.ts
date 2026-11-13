import { App } from "aws-cdk-lib";

/**
 * An App that fingerprints the Lambda asset but does not copy it into each synth's output: the
 * packaged archive-backend is tens of megabytes, and copying it per test makes the suite crawl.
 */
export function testApp(): App {
  return new App({ context: { "aws:cdk:disable-asset-staging": true } });
}
