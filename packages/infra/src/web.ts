import type * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as iam from "aws-cdk-lib/aws-iam";
import type * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface WebProps {
  readonly derivedBucket: s3.IBucket;
  readonly archiveBucket: s3.IBucket;
  readonly restApi: apigateway.RestApi;
}

// Plan 7 changes this when it writes per-dataset pages.
const SITE_REWRITE = `function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith("/")) {
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

  constructor(scope: Construct, id: string, props: WebProps) {
    super(scope, id);
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
}
