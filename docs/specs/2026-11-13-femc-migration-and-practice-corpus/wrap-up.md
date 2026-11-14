---
diazo: research-archive-in-a-box/femc-migration-and-practice-corpus
file: wrap-up
status: printed
hash: d995529ae8e59f493f8b6c5c3f9983558c9a2259d89899e5382e8cac8dda0bc7
rests_on: [PLAN1]
record: README.md
---

# Any dataset downloaded from FEMC's archive can now be turned into a package and audited.

## How it works now

Download a dataset from FEMC's public archive with its EML record, add its row to `practice-data/femc/SOURCES.md`, and run `uv run femc convert <dataset-folder> <out-folder>`. The converter reads FEMC's non-standard EML through the shared importer, takes the columns from the real files, sets rights and access from what FEMC's page shows, and writes a package the contract accepts, with `_build/not-imported.txt` listing everything it could not carry over and `_build/project.json` keeping the project record. `cruise diagnose` and `cruise audit --config examples/femc/archive.yaml` then show what each dataset needs before it could be published. Ten FEMC datasets are converted this way on your machine: tables, a shapefile set, a raster, photographs, a linked record, and records FEMC shares only on request or holds only as a description.

## Results

- The `femc` converter and FEMC's archive config in `examples/femc/`, with the shared contract and cruise unchanged: PLAN1, schuettc/research-in-a-box#23
- All ten practice datasets converted with no structure findings; the counts for the FEMC report (errors, warnings, notes, score and rules fired, with no data values) in `documents/femc-audit-counts.md`: PLAN1, schuettc/research-in-a-box#23
- The approved spec and three Decision log lines in `docs/planning-handoff.md` (the FEMC contact moves to Plan 10b, the converter's place, the ten-dataset corpus): PLAN1, schuettc/research-in-a-box#18

## Different from the plan

The four new datasets were downloaded by the agent at your word rather than by hand. The final review found that each project's description and people were used only in the README, so the converter now keeps the project record in `_build/project.json`. CI's formatting check failed once on a test fixture that the local Python checks don't cover, and was fixed in the same PR.
