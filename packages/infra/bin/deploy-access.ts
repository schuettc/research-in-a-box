// Its own CDK app, so the default app and CI's deploy never touch it:
//   npx cdk --app "npx tsx bin/deploy-access.ts" deploy -c githubRepo=<owner>/<name>
import { fileURLToPath, pathToFileURL } from "node:url";
import { App, Stack, Tags } from "aws-cdk-lib";
import { loadArchiveConfig, stagesOf } from "../src/config";
import { DeployAccess } from "../src/deploy-access";

const ARCHIVE_YAML = fileURLToPath(new URL("../../../archive.yaml", import.meta.url));
const REPO_PATTERN = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

export const DEPLOY_STACK_NAME = "ResearchArchiveDeploy";

export interface DeployEnv {
  readonly account?: string;
  readonly region?: string;
}

/**
 * The deploy-access app: the repo from the `githubRepo` context value, and the stages of the
 * config whose account is the one being deployed to or is unset.
 */
export function createDeployAccessApp(
  configPath: string = process.env.ARCHIVE_CONFIG ?? ARCHIVE_YAML,
  context: Record<string, string> = {},
  env: DeployEnv = {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
): App {
  const app = new App({ context });
  const githubRepo: unknown = app.node.tryGetContext("githubRepo");
  if (typeof githubRepo !== "string" || githubRepo === "") {
    throw new Error("githubRepo is required: run with -c githubRepo=<owner>/<name>");
  }
  if (!REPO_PATTERN.test(githubRepo)) {
    throw new Error(`githubRepo must be <owner>/<name>, not "${githubRepo}"`);
  }
  const stages = stagesOf(loadArchiveConfig(configPath))
    .filter((stage) => !stage.account || stage.account === env.account)
    .map((stage) => stage.name);
  if (stages.length === 0) {
    throw new Error(`no stage in the config deploys to account ${env.account ?? "(unknown)"}`);
  }
  const stack = new Stack(app, DEPLOY_STACK_NAME, {
    env: env.account || env.region ? { account: env.account, region: env.region } : undefined,
  });
  new DeployAccess(stack, "DeployAccess", { githubRepo, stages });
  Tags.of(app).add("Repo", "schuettc/research-in-a-box");
  return app;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  createDeployAccessApp().synth();
}
