import { Construct } from "constructs";
import { stagesOf } from "./config";
import type { ArchiveConfig } from "./generated/archive-config";

export interface ResearchArchiveProps {
  readonly config: ArchiveConfig;
  readonly stage: string;
}

export class ResearchArchive extends Construct {
  readonly isProd: boolean;

  constructor(scope: Construct, id: string, props: ResearchArchiveProps) {
    super(scope, id);
    if (!stagesOf(props.config).some((stage) => stage.name === props.stage)) {
      throw new Error(`stage "${props.stage}" is not in infrastructure.stages`);
    }
    this.isProd = props.stage === "prod";
  }
}
