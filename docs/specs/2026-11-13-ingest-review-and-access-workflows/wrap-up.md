---
diazo: research-archive-in-a-box/ingest-review-and-access-workflows
file: wrap-up
status: out of date (PLAN2 added)
hash: 26e49bfa81685d1930d8835a6404ba2e951af17374c10054b272e028fa86ab33
rests_on: [PLAN1]
record: README.md
---

# A contributor can now submit a package, a curator can review it, and an approved package is published and findable.

## How it works now

A contributor creates a submission, uploads the package with links that S3 checks against each file's checksum, and submits it. GuardDuty scans every file, cruise runs the structure and quality checks, and a package with a blocking error goes straight back to the contributor with its findings. Under the review policy an admin sets at run time (review on or off, skip rules, two-curator cases, named reviewers per theme, reminders and a stale mark), a curator approves, rejects or requests changes, and a request for changes loops back through the checks when the contributor resubmits. An approved package gets its version, a checksummed copy under the archive's open or restricted prefix, its catalog entries and its own dataset page at `/datasets/<id>`. Curators get an email when a submission waits for them, and every step is an event in the audit log.

## Results

- The review policy model and the `archive:published` field in the contract: PLAN1, research-in-a-box#21
- The archive-config parameter and the shared config reader, split out early for Plan 6: PLAN1, research-in-a-box#28
- The submissions API, the durable ingest, publish, dataset pages, the Ingest construct and `just ingest-e2e`: PLAN1, research-in-a-box#29

## Different from the plan

You chose not to wait a day for the reminder email (DCSN4), so the reminder never fired on AWS; it is covered by unit tests only (PARK17). The final review ran on Claude Opus, not OpenAI, because OpenAI's usage limit was reached. The test stage was deployed and run a second time after Plan 6's first plan landed underneath, and its first teardown got stuck on a waiting submission (PARK19).
