---
diazo: research-archive-in-a-box/femc-findings-report
file: PLAN1
status: approved
approved: 2026-11-14T00:58:19-06:00
hash: 76fde1a08adfa67d816af344eabe550fdffc168e39621e50cfbf232251518c99
rests_on: [AGNT1, AGNT2, AGNT3, AGNT4, AGNT5, DCSN1, DCSN2]
record: README.md
---

# PLAN1: Write the FEMC report

## Spec

`spec.md` in this folder: the report in the handoff's eight sections, written now from the ten-dataset corpus, with the Ozone before-and-after filled only from FEMC's own sources, kept in gitignored `practice-data/report/`, and sent by Court.

## The change

Four files and one folder under `practice-data/report/`, none committed:

- `notes.md`: the working notes. Every claim the report makes, with the command that checks it and that command's real output.
- `ozone-after/`: the converted Ozone package re-packaged by hand from FEMC's own public sources, with its `changes.jsonl` and its audit.
- `femc-report.md`: the report.
- `femc-report.pdf`: rendered from it.

No code in the repo changes. The only repo change is this folder's record.

Risk: a wrong or unkind claim reaches FEMC; undone only by a correction email from Court. So every claim is traced in `notes.md` before the report cites it, and a reviewer from the other model family checks a sample and the tone. Cost to Court: reading the draft and sending it.

## Left out

- Contacting FEMC, any new code, any further download, a hosted page, and committing the report (spec's Left out).
- A second before-and-after dataset.

## Where

- `practice-data/femc/` (the ten downloads, `SOURCES.md`), `practice-data/packages/` (the converted packages), `practice-data/audit/audit.json` (the full audit).
- `docs/specs/2026-11-13-femc-migration-and-practice-corpus/documents/femc-audit-counts.md` on `main` (the counts).
- `examples/femc/archive.yaml` (the config the audit runs with).
- Plan 6's planning folder, `docs/specs/2026-11-13-api-and-search/`, for its record of the 22 searches once it is on `main`.

Every task works in the primary clone's `practice-data/` (it exists only there) and writes nothing inside the repo's tracked files.

### Task 1: The evidence notes

**Does:** Writes `practice-data/report/notes.md`: one entry per finding in the spec's section 3 and per strength in section 1, each with the dataset's FEMC page (from `SOURCES.md`), the field, the EML package id, the command that checks it and its real output. Re-runs `cruise audit --config examples/femc/archive.yaml --json` over the ten packages and confirms the counts still match `femc-audit-counts.md`. Checks whether Plan 6's record of its 22 searches is on `origin/main`; if it is, records the numbers with the file they come from, and if not, records that the Camels Hump finding rests on its record alone.
**Files:** `practice-data/report/notes.md` (new, not committed)
**Checks:** `uv run cruise audit --config examples/femc/archive.yaml --json practice-data/packages/<each of the ten>` (exit 1 is expected: the packages have errors; the check is that the counts match); `git status --porcelain practice-data` (prints nothing)
**Serves:** none (rests on calls AGNT4, AGNT5)

The creator finding is written as call AGNT3 words it: no creator on the dataset, people on the parent project under FEMC's own role tags. A finding the raw record doesn't bear out is dropped from the report and noted as dropped.

### Task 2: The Ozone after-package

**Does:** Copies `practice-data/packages/ozone-bioindicators/` to `practice-data/report/ozone-after/` and fills, by hand, only what FEMC publishes elsewhere: creators from the project record's people (`_build/project.json`), rights from what FEMC's page shows, and a description from the record's own project text. Adds one line per fill to `changes.jsonl` in the contract's Change shape, each naming its FEMC source, and rewrites `checksums.sha256` so structure validation passes. Re-audits it and records before and after counts in `notes.md`, with the list of gaps only FEMC can fill (methods, geographic coverage, the missing units, the undescribed columns, the species code list).
**Files:** `practice-data/report/ozone-after/` (new, not committed), `practice-data/report/notes.md`
**Checks:** `uv run cruise diagnose practice-data/report/ozone-after` (no structure errors); `uv run cruise audit --config examples/femc/archive.yaml practice-data/report/ozone-after` (fewer errors than the original's 3)
**Serves:** DCSN2, DCSN1

Nothing is filled from a guess. If a field can only be filled by inventing a value, it stays empty and goes on the "only you can fill this" list.

### Task 3: The report

**Does:** Writes `practice-data/report/femc-report.md` in the spec's eight sections, addressed to Court's FEMC contact (name left as a placeholder for Court) and forwardable unchanged. Section 1 first and specific; section 3's findings each link the dataset page, name the field and give counts from `notes.md`; section 4 shows Ozone before and after with both scores; section 5 says plainly which parts of the kit are built and which are planned; section 6 the migration path; section 7 the quick fixes; section 8 the questions, with the bulk-export request. Plain language for archive staff, collaborative, and honest that we saw only public pages and ten datasets. Every claim in it has an entry in `notes.md`.
**Files:** `practice-data/report/femc-report.md` (new, not committed)
**Checks:** `grep -c '^## ' practice-data/report/femc-report.md` (8); `git status --porcelain practice-data` (prints nothing)
**Serves:** DCSN1 (rests on calls AGNT1, AGNT3, AGNT5)

### Task 4: Review and the PDF

**Does:** A reviewer from the other model family (OpenAI, `openai-codex`) picks ten claims from the report, checks each against `practice-data/` and `notes.md`, and reads each section for tone toward people who have kept this data for decades. Findings are handled per receiving-code-review: a wrong claim is fixed or cut. Then renders the PDF: pandoc to standalone HTML with a plain stylesheet, printed to PDF by headless Chrome.
**Files:** `practice-data/report/femc-report.md`, `practice-data/report/femc-report.pdf` (new, not committed)
**Checks:** `pandoc practice-data/report/femc-report.md -s -o practice-data/report/femc-report.html`; `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --print-to-pdf=practice-data/report/femc-report.pdf practice-data/report/femc-report.html`; the reviewer's ten claims all hold after fixes
**Serves:** DCSN1 (rests on calls AGNT2, AGNT4)

The end look, Court reading the PDF and saying it can go as is, is the sign-off card's try list.
