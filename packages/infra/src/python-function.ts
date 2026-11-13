import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Duration, RemovalPolicy } from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import type { Construct } from "constructs";

/** Where `just lambda-assets` installs archive-backend and its arm64 wheels. */
export const PYTHON_ASSETS = fileURLToPath(new URL("../assets/python", import.meta.url));

export interface PythonFunctionProps {
  /** A dotted path in archive_backend, such as `archive_backend.health.handler`. */
  readonly handler: string;
  readonly environment?: Record<string, string>;
  readonly timeout?: Duration;
  readonly memorySize?: number;
}

/** An arm64 Python 3.13 Lambda from the packaged archive-backend, with a one-month log group. */
export function makePythonFunction(
  scope: Construct,
  id: string,
  props: PythonFunctionProps & { readonly isProd: boolean },
): lambda.Function {
  if (!existsSync(PYTHON_ASSETS)) {
    throw new Error("run just lambda-assets first");
  }
  const logGroup = new logs.LogGroup(scope, `${id}Logs`, {
    retention: logs.RetentionDays.ONE_MONTH,
    removalPolicy: props.isProd ? RemovalPolicy.RETAIN : RemovalPolicy.DESTROY,
  });
  return new lambda.Function(scope, id, {
    runtime: lambda.Runtime.PYTHON_3_13,
    architecture: lambda.Architecture.ARM_64,
    code: lambda.Code.fromAsset(PYTHON_ASSETS),
    handler: props.handler,
    environment: props.environment,
    timeout: props.timeout ?? Duration.seconds(30),
    memorySize: props.memorySize ?? 512,
    logGroup,
  });
}
