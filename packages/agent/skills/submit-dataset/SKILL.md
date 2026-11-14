---
name: submit-dataset
description: Checks a local dataset package with the archive's own rules, drafts fixes for what it finds, applies only the ones the person approves, and submits the package to their research-in-a-box archive for review. Use when someone wants to check, fix, finish or submit a dataset package (a folder with datapackage.json), or asks about a submission's status or a curator's requested changes. Submitting needs an account in the contributor group.
---

# Submit a dataset

The checks are the same `cruise` rules the archive's ingest runs, so a package that passes
here passes there. You draft; the person decides. **Never write to the manifest or send
anything to the archive without the person's yes.** The tools come from the
`research-archive` MCP server; `diagnose` and `edit_manifest` work offline.

## Steps

1. **Ask for the package folder and call `diagnose` on it.** Show the `verdict`, the score
   (`quality.score`, with `find`, `understand` and `trust`) and the findings grouped by
   question, errors first:
   - Structure (`structure.*`): the package's files, hashes and references.
   - Can I find, cite and reuse it? (`package.*`)
   - Can I understand each column? (`field.*`)
   - Can I trust the values? (`values.*`)
2. **Draft a fix for each finding you can help with**: a missing title, description,
   keywords, license or rights status, temporal or spatial coverage, methods, contributors,
   or a column's title, description or unit. Draft from what the folder holds: its `docs/`,
   its column names and values, its original files. Show each draft beside its finding.
   **Never invent a fact the folder doesn't support**: where it is silent (who made it, the
   license, the units, how values were measured), ask the person instead of guessing.
   Findings about the data itself (constant columns, out-of-range values, undocumented codes)
   aren't fixed by an edit: explain them and leave the decision to the person.
3. **Stop for the person's yes on each draft.** Apply only the approved ones with
   `edit_manifest`: each edit is `{"target", "value"}`, plus `"resource"` and `"column"` for
   a column. It rewrites `datapackage.json`, `README.md` and `checksums.sha256`, or writes
   nothing and names each failing edit; fix those with the person and try again. Then call
   `diagnose` again and show what changed.
4. **Repeat** until no errors are left or the person stops. Warnings may remain: list them
   and say they don't block publishing.
5. **Submit only with the person's yes.** Say what will happen: every file in
   `checksums.sha256` is uploaded and the package goes to the archive's review. Call
   `sign_in` if needed (say first that it opens the browser), then `submit` with the folder.
   Show the submission id and its status. `submit` refuses a package with an error finding;
   go back to step 2 if it does.
6. **Later, on request, call `submissions`** with the id to show its status. When it is
   `needs-changes`, show the curator's note (in its `decided` event) and the findings (in
   its `report`; if it answers a `report_error` instead, say the findings couldn't be read
   and why, and run `diagnose` on the folder to see them), go back to step 2, and call
   `submit` with the folder and `submission` set to the same id for its next round.

## When a tool answers an error

Say what the tool said in plain words, keep working locally (`diagnose` and `edit_manifest`
need no network), and say what to run again:

- **No archive is set**: ask for the archive's web address and call `connect`.
- **The archive can't be reached**: the package stays as it is on disk; run `submit` again
  when the archive answers. Nothing is queued. A submit that failed part way leaves a draft
  in the archive that expires on its own; the next `submit` starts a fresh one.
- **Signed out or the sign-in expired**: sign-in lasts an hour and only while this session
  runs. Call `sign_in` again (with their go) and retry.
- **Not allowed** (it names the group): submitting needs the `contributor` group; the
  archive's admin can add it.
- **Conflict** (the archive's message): the submission isn't in a state that takes this step,
  such as one already in review. Call `submissions` to see where it stands.
- **Refused** (the archive's message): pass it on, and fix what it names with the person.
