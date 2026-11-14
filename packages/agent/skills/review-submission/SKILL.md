---
name: review-submission
description: Helps a curator review submissions waiting in their research-in-a-box archive, reading each one's metadata and files, summarising what it is and the judgment calls no rule can make, and drafting a decision and note that is sent only with the curator's yes. Use when a curator asks what is waiting for review, wants to review, approve, reject or request changes on a submission. Needs an account in the curator group.
---

# Review a submission

The rules have already run; this is the part they can't do. You read and summarise; the
curator decides. **Never call `decide` without the curator's yes on the exact decision and
note.** The tools come from the `research-archive` MCP server.

## Steps

1. **Call `sign_in`** (say first that it opens the browser), then `submissions` with the
   queue (`queue: true`). Show what waits in review, stale ones first: id, who submitted
   it, the dataset it versions (if any) and how long it has waited. The title comes from
   its `datapackage.json`, read in step 2.
2. **For the one the curator picks, read it.** Call `submissions` with its id for its status,
   events and findings `report`, then `submission_files` for short-lived links to its
   current files. If it answers a `report_error` instead of a `report`, tell the curator
   the findings couldn't be read and why (the `report_error` text), and say the summary
   below rests on the files alone.
   Read its `datapackage.json` and a sample of each table (the first rows of each CSV) from
   those links. The links expire after a few minutes: call `submission_files` again if one
   has.
3. **Summarise it**, each point citing the field, column or row it rests on:
   - what the data is: its subject, place, period and size;
   - how complete the metadata is: the score, and what is missing;
   - the warnings the rules raised, and whether they matter here;
   - the judgment calls no rule can make: a column that looks like a location id with no
     grid described, a license that doesn't fit the stated source, a description that
     contradicts the values, units that don't fit the numbers, personal or sensitive data.
     Say plainly what you couldn't check.
4. **Draft a decision and a note**: `approve`, `request-changes` or `reject`, with a note
   the submitter can act on (for changes, each change named with the field or column). Show
   both, and change them as the curator asks.
5. **Only with the curator's yes, call `decide`** with the id, the decision and the note.
   It answers only that the decision was accepted (`submissionId` and `decision`); an
   approval is published afterwards, on its own. Say the decision was accepted, then call
   `submissions` with the id and report its status as it stands. Say it is published, and
   give `/datasets/<id>` on the archive, only once that status is `published`.

## When a tool answers an error

Say what the tool said in plain words, and what to do next:

- **No archive is set**: ask for the archive's web address and call `connect`.
- **The archive can't be reached**: nothing was decided; run the step again when it
  answers. Nothing is queued.
- **Signed out or the sign-in expired**: sign-in lasts an hour and only while this session
  runs. Call `sign_in` again (with their go) and retry.
- **Not allowed** (it names the group): reviewing needs the `curator` group; the archive's
  admin can add it.
- **The submission isn't in review** (from `submission_files`), or another **conflict**:
  someone may have decided it already. Call `submissions` with its id to see where it stands.
- **Refused** (the archive's message): pass it on.
