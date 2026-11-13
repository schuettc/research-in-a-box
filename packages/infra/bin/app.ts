import { pathToFileURL } from "node:url";
import { App, Stack, Tags } from "aws-cdk-lib";
import { ResearchArchive } from "../src/research-archive";

export const STACK_NAME = "ResearchArchive";

export function createApp(): App {
  const app = new App();
  const stack = new Stack(app, STACK_NAME);
  new ResearchArchive(stack, "Archive");
  Tags.of(app).add("Repo", "schuettc/research-in-a-box");
  return app;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  createApp().synth();
}
