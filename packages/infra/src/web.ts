import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as iam from "aws-cdk-lib/aws-iam";
import type * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import { Construct } from "constructs";

const WEB_BUILD = fileURLToPath(new URL("../../web/dist", import.meta.url));

/** What /auth-config.json tells the web app and the CLI: the fields Plan 9 agreed. */
export interface AuthConfig {
  readonly region: string;
  readonly cognitoDomain: string;
  readonly webClientId: string;
  readonly cliClientId: string;
}

export interface WebProps {
  readonly derivedBucket: s3.IBucket;
  readonly archiveBucket: s3.IBucket;
  readonly restApi: apigateway.RestApi;
}

// /datasets/<id> and /datasets/<id>/ read the dataset's own page; any other extensionless path
// is the app's.
const SITE_REWRITE = `function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var dataset = uri.match(/^\\/datasets\\/([^\\/.]+)\\/?$/);
  if (dataset) {
    request.uri = "/datasets/" + dataset[1] + "/index.html";
  } else if (uri.endsWith("/")) {
    request.uri = uri + "index.html";
  } else if (uri.substring(uri.lastIndexOf("/") + 1).indexOf(".") === -1) {
    request.uri = "/index.html";
  }
  return request;
}`;

// /data/<datasetId>/<version>/<path> reads open/<datasetId>/<version>/<path>.
const STRIP_DATA = `function handler(event) {
  var request = event.request;
  request.uri = request.uri.replace(/^\\/data/, "");
  return request;
}`;

/**
 * One distribution: the app from the derived bucket's `site/`, open data from the archive
 * bucket's `open/` under `/data`, and the API under `/api`. No distribution-wide error
 * responses, so a missing data file or an API 404 stays a 404.
 */
export class Web extends Construct {
  readonly distribution: cloudfront.Distribution;
  private readonly derivedBucket: s3.IBucket;

  constructor(scope: Construct, id: string, props: WebProps) {
    super(scope, id);
    this.derivedBucket = props.derivedBucket;
    const viewerRequest = (functionId: string, code: string): cloudfront.FunctionAssociation => ({
      eventType: cloudfront.FunctionEventType.VIEWER_REQUEST,
      function: new cloudfront.Function(this, functionId, {
        code: cloudfront.FunctionCode.fromInline(code),
        runtime: cloudfront.FunctionRuntime.JS_2_0,
      }),
    });

    this.distribution = new cloudfront.Distribution(this, "Distribution", {
      defaultRootObject: "index.html",
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(props.derivedBucket, {
          originPath: "/site",
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        functionAssociations: [viewerRequest("SiteRewrite", SITE_REWRITE)],
      },
      additionalBehaviors: {
        "/data/*": {
          origin: origins.S3BucketOrigin.withOriginAccessControl(props.archiveBucket, {
            originPath: "/open",
          }),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD,
          cachedMethods: cloudfront.CachedMethods.CACHE_GET_HEAD,
          cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
          functionAssociations: [viewerRequest("StripData", STRIP_DATA)],
        },
        "/api/*": {
          origin: new origins.RestApiOrigin(props.restApi),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
          cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
          originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER,
        },
      },
      enableLogging: true,
      logBucket: props.derivedBucket,
      logFilePrefix: "logs/",
    });

    // Origin access control grants CloudFront the whole archive bucket; restricted data is
    // reached only through the API's short-lived links, so CloudFront is denied it outright.
    props.archiveBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.DENY,
        principals: [new iam.ServicePrincipal("cloudfront.amazonaws.com")],
        actions: ["s3:GetObject"],
        resources: [props.archiveBucket.arnForObjects("restricted/*")],
      }),
    );
  }

  /**
   * Upload the web build and /auth-config.json into the derived bucket's `site/`. Pruning is
   * off in both deployments: catalog.json and datasets/ share the folder. The hashed assets
   * cache for a year and go first; index.html, app.js and auth-config.json are no-cache and
   * invalidated, so a release reaches readers at once.
   */
  deploySite(authConfig: AuthConfig): void {
    if (!existsSync(WEB_BUILD)) {
      throw new Error("packages/web/dist is missing: run npm run build -w packages/web first");
    }
    const assets = new s3deploy.BucketDeployment(this, "SiteAssets", {
      sources: [s3deploy.Source.asset(WEB_BUILD, { exclude: ["index.html", "app.js"] })],
      destinationBucket: this.derivedBucket,
      destinationKeyPrefix: "site/",
      prune: false,
      cacheControl: [s3deploy.CacheControl.fromString("public, max-age=31536000, immutable")],
    });
    const site = new s3deploy.BucketDeployment(this, "Site", {
      sources: [
        s3deploy.Source.asset(WEB_BUILD, { exclude: ["*", "!index.html", "!app.js"] }),
        s3deploy.Source.jsonData("auth-config.json", { ...authConfig }),
      ],
      destinationBucket: this.derivedBucket,
      destinationKeyPrefix: "site/",
      prune: false,
      cacheControl: [s3deploy.CacheControl.noCache()],
      distribution: this.distribution,
      distributionPaths: ["/index.html", "/app.js", "/auth-config.json"],
    });
    site.node.addDependency(assets);
  }
}
