---
diazo: research-archive-in-a-box/repo-layout-and-conventions
file: wrap-up
status: printed
hash: ea6594e39ade1d70f9bad10e48bfd644faad5fd5c5435278b60a1383547f68bd
rests_on: [PLAN1]
record: README.md
---

# research-in-a-box now exists as one public repo with an empty, passing skeleton that every other plan builds on.

## How it works now

The repo is public at https://github.com/schuettc/research-in-a-box. It holds a uv workspace with three Python packages (`archive-contract`, `cruise` and the backend) and an npm workspace with the `ResearchArchive` CDK construct and the web app. One command, `just check`, runs every lint, type check and test plus the schema drift check, and CI runs the same recipes on every push. Anyone can install the local tool straight from GitHub with `uv tool install "git+https://github.com/schuettc/research-in-a-box#subdirectory=packages/tool"`, with nothing published to PyPI. Plan 2 is already building the contract inside this layout.

## Results

- The empty skeleton, its checks and the CI and release workflows: PLAN1, pushed as 712dcca to schuettc/research-in-a-box, CI run 43445991147 green.

## Different from the plan

The sample package moved to Plan 2 during planning, so the skeleton commits no data. The note to Plan 2 after the first commit was skipped, because this session owns Plan 2's folder too.
