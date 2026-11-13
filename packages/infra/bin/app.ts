import { fileURLToPath, pathToFileURL } from "node:url";
import { App, Stack, Tags } from "aws-cdk-lib";
import { loadArchiveConfig, stagesOf } from "../src/config";
import { ResearchArchive } from "../src/research-archive";

const ARCHIVE_YAML = fileURLToPath(new URL("../../../archive.yaml", import.meta.url));

export function stackName(stage: string): string {
  return `ResearchArchive-${stage}`;
}

/** The config file: `ARCHIVE_CONFIG` when set, so a test stage needs no edit to archive.yaml. */
export function createApp(configPath: string = process.env.ARCHIVE_CONFIG ?? ARCHIVE_YAML): App {
  const config = loadArchiveConfig(configPath);
  const app = new App();
  for (const stage of stagesOf(config)) {
    const env =
      stage.account || stage.region
        ? { account: stage.account ?? undefined, region: stage.region ?? undefined }
        : undefined;
    const stack = new Stack(app, stackName(stage.name), { env });
    new ResearchArchive(stack, "Archive", { config, stage: stage.name });
  }
  Tags.of(app).add("Repo", "schuettc/research-in-a-box");
  return app;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  createApp().synth();
}
