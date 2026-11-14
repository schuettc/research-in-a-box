---
diazo: research-archive-in-a-box/ingest-review-and-access-workflows
file: PLAN2
status: approved
approved: 2026-11-14T13:36:53-06:00
hash: f4aa7639f6ff9b457d11c9ccaac6a04fe0a85fee0f738d39ba3bad3aca0fc5a2
rests_on: [AGNT1, AGNT9]
record: README.md
---

# PLAN2: The curator files route and the shared page writer

## Spec

`spec.md` in this folder, approved, plus two follow-ups from PLAN1 that other plans now wait on. PARK15 is the curator files route, which Plan 9's review skill (its `submission_files` tool, already on `main` as #44) and Plan 8's curator screen need. PARK16 is the shared page writer, which Plan 8's reindex needs to rebuild every dataset page. Both shapes were agreed with the coordinating session and Plan 9 (muster threads 964 and 990).

## The change

- **The files route.** `GET /api/submissions/{id}/files` lets a curator read a held package. It answers `{"round": <n>, "files": [{"path", "size", "sha256", "url"}]}`:
  - `path`, `size` and `sha256` come from the submission item's `files[round]`, the same entries create takes.
  - `url` is a five-minute presigned GET of `held/<id>/<path>`.
  - It signs only the listed paths.
  - Errors: 403 for anyone outside the curator group, 404 for an unknown id, and 409 unless the status is `in-review` or `publishing`. Those are the only states in which `held/<id>/` exists.
- **The shared page writer.** `pages.write_page(s3, bucket, html, dataset_id)` takes over the S3 write that sits inside ingest's durable `_page` step today (key `site/datasets/<id>/index.html`, its content type, and `max-age=300`). The `_page` step calls it, so Plan 8's reindex calls only `pages.write_page` and never edits ingest. `render_page`'s signature doesn't change.

## Left out

No change to the review flow or to the page template. Plan 8 owns the template. No deployed run of its own: Plan 9's walk on a test stage calls the files route end to end, and Plan 8's reindex calls `write_page`. Risk: the route is read-only and curator-only, and it signs five-minute links to files a curator is already asked to judge. A mistake shows a curator a file early or not at all, and it is undone by a fix. Cost: no step for you beyond approving this plan.

## Where

Branch `plan7/files-route` from `origin/main`, in the worktree `.worktrees/research-archive-in-a-box/plan7/files-route`. One pull request with auto-merge on (`main` is protected and needs the python, typescript and security checks). The PR carries its Decision log row in `docs/planning-handoff.md`.

### Task 8: The curator files route

**Does:** Adds `files(c, env, caller, sid)` to `archive_backend.submissions`, routed as `("GET", "/api/submissions/{id}/files")`, with the answer and refusals given under The change. In `packages/infra/src/ingest.ts`, adds the `files` resource under `{id}` with a GET method behind the authorizer, and gives the submissions function `s3:GetObject` on `held/*`, which signing needs. Adds the Decision log row for the route and its shape.
**Files:** `packages/backend/src/archive_backend/submissions.py`, `packages/backend/tests/test_submissions.py`, `packages/infra/src/ingest.ts`, `packages/infra/test/ingest.test.ts`, `docs/planning-handoff.md`
**Checks:** `just check`
**Serves:** none (rests on call AGNT1)

Tests: a curator gets one URL per listed file, each for `held/<id>/<path>` and expiring in 300 seconds; a contributor (even the submitter) gets 403; an unknown id gets 404; each status other than `in-review` and `publishing` gets 409; a path not in `files[round]` is never signed. The synth test finds the route under `{id}` behind the authorizer, and the `held/*` read on the submissions role only.

### Task 9: The shared page writer

**Does:** Adds `write_page(s3, bucket, html, dataset_id) -> str` to `archive_backend.pages`. It writes `site/datasets/<id>/index.html` with `ContentType: text/html; charset=utf-8` and `CacheControl: max-age=300`, and returns the key. Ingest's durable `_page` step calls it in place of its own `put_object`.
**Files:** `packages/backend/src/archive_backend/pages.py`, `packages/backend/src/archive_backend/ingest.py`, `packages/backend/tests/test_pages.py`, `packages/backend/tests/test_publish.py` if its assertions name the inline write
**Checks:** `just check`
**Serves:** none (rests on call AGNT9)

Tests: `write_page` writes the key, content type and cache header to a stubbed S3 and returns the key, and the existing publish test still finds the page at the same key with the same headers.
