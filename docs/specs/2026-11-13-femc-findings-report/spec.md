---
diazo: research-archive-in-a-box/femc-findings-report
file: spec
status: approved
approved: 2026-11-14T00:56:57-06:00
hash: 0f1405e6b9ab20c2ad576dad5f919e74148188c7b5318415cc46842ad7557f25
rests_on: [AGNT3, AGNT4, AGNT5, DCSN2, DCSN1, AGNT1, AGNT2]
record: README.md
---

# The FEMC report

## Goal

A short, plain-language report that shows FEMC's archive staff and partners what we found in their own data and what the kit would do about it. It is written now, whole, from the ten-dataset practice corpus and Plan 5's audit counts, and it asks FEMC for a bulk export as one of its questions. Court sends it to their FEMC contact; this plan writes it and makes no contact itself.

## The report, section by section

The report follows the handoff's eight sections. Each section's sources are fixed here, so every sentence can be traced.

| # | Section | What it says | Sources |
| --- | --- | --- | --- |
| 1 | What the archive does well | Specific strengths, stated first: an EML record for every dataset, stable package ids, a parent project for every dataset, five access states including Linked, six browsing themes (air, climate change, forest, soil, water, wildlife, as FEMC's themes page shows on 2026-11-14; the handoff's seven counts the All Projects tab), anonymous downloads with an optional usage form that supports their funding case, and decades of monitoring data kept safe. | FEMC's public pages (the handoff's "From their public pages"), the ten EML records |
| 2 | What we looked at | The ten datasets by name with a link to each FEMC page, the dates downloaded (2026-11-12 and 2026-11-13), how (anonymous public downloads, the usage form left blank, under FEMC's data policy), and what we did not see (anything behind an account, the database behind the CSV exports, any other dataset). | `practice-data/femc/SOURCES.md` |
| 3 | What we found | The findings below, each naming a dataset page and a field, with counts from the audit. | `practice-data/femc/*/eml.xml`, Plan 5's `documents/femc-audit-counts.md`, `practice-data/audit/audit.json`, `practice-data/packages/*/_build/not-imported.txt` |
| 4 | Before and after | Ozone Bioindicators as its record stands today, beside the same dataset as a package filled only from FEMC's own public sources, with both audit scores and the gaps only FEMC can fill. | The Ozone package of the next section |
| 5 | What the kit offers | Their daily work (taking in a submission, checking it, publishing it, answering a request, reporting use) mapped to what the kit does, saying plainly which parts are built today and which are planned. | The handoff's plan briefs and the Decision log; what is merged on `main` |
| 6 | What adopting it would take | A migration path from their existing EML: the `femc` converter already turns all ten records into packages that pass structure checks; what a full migration would need from them (the bulk export, their decisions on licenses and required fields); running the archive in their own AWS account. | Plan 5's wrap-up, `examples/femc/` |
| 7 | Quick fixes they can make now | Changes in their own system that help with or without the kit: put the license shown on the page into the EML, name the dataset's creators on the dataset as well as the project, fix the `distibution` tag, give linked records a real title, description and the external data URL, and describe each column with its unit. | The findings in section 3 |
| 8 | Questions for them | Whether they would share a bulk export of their EML records (and, where licenses allow, their tables) so the audit can cover the whole archive; which licenses the "third party determines" datasets carry; whether the people on the project are the dataset's authors; what they would want from the kit first. | Gaps left by sections 3 and 4 |

The findings section 3 rests on, each checked against the raw records:

- None of the ten dataset records names a creator, methods or a geographic coverage. People are recorded on the parent project under FEMC's own role tags (principal investigator, content provider), so EML readers don't see them as the dataset's authors. (10 of 10 records.)
- No EML record carries a license, including the two whose pages show one (CC0 on Vegetation Class Raster, CC BY-NC-SA 4.0 on Mount Mansfield Quadrat Images); four pages show no license at all. (10 of 10 records, 4 of 10 pages.)
- Record and file disagree in 3 of 5 tables: columns in the file with no description (the aerial survey, FIA), and described columns missing from the file (Data Rescue Inventory's AboutP1, AboutP2 and others), each named in the converter's not-imported list.
- Camels Hump's dataset is titled `census_data` and described as "Github repo of census_data"; its place name appears only on the parent project, and its data's address only inside the citation text, while its download link points back to FEMC's own page.
- Column-level gaps, as audit counts across the ten: units missing 328 times, descriptions repeating the column name 249 times, placeholder values 203 times, descriptions missing 168 times, columns holding one value in every row 66 times.
- Every record uses the misspelled `distibution` tag, so standard EML tools miss each dataset's download link.

Rests on: AGNT3, AGNT4, AGNT5

## The Ozone before-and-after

Section 4 shows Ozone Bioindicators twice. "Before" is its FEMC record as it stands, with today's audit: 3 errors, 24 warnings, 1 note, score 76.

"After" is the converted Ozone package re-packaged by hand, filling only what FEMC already publishes somewhere else: the people from the project record as creators, the rights from what FEMC's page shows, and a title and description from the record's own project text. Each fill is a line in the package's `changes.jsonl` naming where it came from. The package is audited again with `cruise audit --config examples/femc/archive.yaml`, and the report shows the new score.

What stays open is listed as "only you can fill this": the methods, the geographic coverage, the 14 missing units, the four columns with no description and the code list for the species column. These feed section 7 and section 8. Nothing is filled from our own guess.

The hand-made package lives in `practice-data/report/ozone-after/`, beside the report, and is never committed.

Rests on: DCSN2, DCSN1

## Where it lives and how it reaches FEMC

The report is a Markdown file, `practice-data/report/femc-report.md`, rendered to `practice-data/report/femc-report.pdf`. `practice-data/` is gitignored, so neither the drafts, the PDF nor the Ozone package is committed to the public repo. This folder's record names the path and holds no copy.

It is addressed to Court's FEMC contact by name and written so it can be forwarded unchanged to archive staff and partners. Court attaches the PDF to an email of their own; whether and when to send it is Court's call. Once FEMC has seen it, a version can be committed if they agree; that is a follow-up, not part of this plan.

Every finding links the dataset's FEMC page from `SOURCES.md`, names the field, and gives the EML package id in brackets where a field-level check needs it. Counts come only from `cruise audit` output or a command whose output is in the report's working notes, never from a relayed message: Plan 6's search numbers are quoted only once Plan 6's own record of its searches is on `main`, and otherwise the Camels Hump finding rests on its record alone.

Risk: a wrong or unkind claim reaches FEMC and costs Court the relationship; it is undone only by a correction email. Checks are sized to that: every claim is traced to its source before Court reads it. Cost to Court: reading the draft, and one send.

Rests on: DCSN1, AGNT1, AGNT2, AGNT4, AGNT5

## Left out

- Contacting FEMC: Court sends the report.
- Any new code: no report generator, no `cruise tidy`, no change to the converter, contract or cruise.
- Datasets beyond the ten: no more downloads, and no scraping, until FEMC agrees to a bulk export.
- A lighter early version, and a hosted web page.
- Committing any version of the report to the public repo before FEMC has seen it.

Rests on: DCSN1, AGNT2

## How we'll know it works

- `practice-data/report/femc-report.md` has all eight sections, and the PDF renders from it.
- Every finding in section 3 links a FEMC dataset page and names a field; every count matches `femc-audit-counts.md` or a command recorded in the working notes.
- The Ozone "after" package exists, passes `cruise audit` with fewer errors than 3, and every fill in its `changes.jsonl` names a FEMC source.
- A reviewer from the other model family checks ten claims picked from the report against `practice-data/` and finds none wrong, and checks the tone section by section.
- `git status` in the repo shows no file from `practice-data/report/`.
- Court reads it and says it can go as is.

Rests on: DCSN1, DCSN2, AGNT4, AGNT5
