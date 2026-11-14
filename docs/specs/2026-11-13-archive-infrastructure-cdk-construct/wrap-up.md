---
diazo: research-archive-in-a-box/archive-infrastructure-cdk-construct
file: wrap-up
status: printed
hash: d7d217dc63bbfe05ae3e45983e067edc3626c6f1b658a5a53fa5deb30f11457a
rests_on: [PLAN1, PLAN2, PLAN3]
record: README.md
---

# A fork can now deploy a working, empty research archive to its own AWS account from one config file.

## How it works now

You edit the `infrastructure` section of `archive.yaml` (stages, alert email, budget, and switches for WAF and write-once locking), then `cdk deploy` builds one `ResearchArchive-<stage>` stack per stage. The deploy holds the staging, archive and derived buckets, the catalog and operational tables, Cognito sign-in with email, an API behind CloudFront at `/api`, open downloads at `/data/<dataset>/<version>/<file>`, a budget, alarms and a dashboard, and a weekly integrity check that emails you when an archived file no longer matches its package. `just reindex <stage>` rebuilds the catalog from the packages in S3 into the spare table and switches to it only when the load completes cleanly; `just reindex-status <stage>` shows how it went. Plans 6 and 7 attach their endpoints and pipeline to the tables, buckets, user pool and API the construct exposes, and build Python Lambdas the same way through `pythonFunction`.

## Results

- The config section, the generated TypeScript config type and one stack per stage, with the buckets and tables: PLAN1, research-in-a-box#10
- Lambda packaging, operations, Cognito, the API, CloudFront and the integrity check: PLAN2, research-in-a-box#12
- The reindex and its just recipes: PLAN3, research-in-a-box#13
- Four fixes the test deploy found on real AWS (the bulk load's response shape and permission, and two in the status recipe): PLAN3, research-in-a-box#14 and #15
- The test deploy: every check in the spec passed on a stack in account 316091283514, which was then destroyed with nothing left behind: PLAN3
- The decision-log lines Plans 6, 7 and 10a build on, and the planning record: research-in-a-box#7, #8 and #16

## Different from the plan

The coordinating session's review moved the custom domain, ORCID and university sign-in, the vector index and the embeddings setting, download counting and the reindex's catch-up out of Plan 4, to Plan 6 or to follow-ups, before the spec was approved. The final review of PLAN3's code fell back to a Claude reviewer when the OpenAI reviewer hit its usage limit. The test deploy took one extra round: the reindex's first live run failed at the load step, and after #14 and #15 it completed.
