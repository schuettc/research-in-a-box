---
diazo: research-archive-in-a-box/quality-rules-and-local-tool
file: wrap-up
status: printed
hash: 2d379e72b4d0fcd86be41fd7228ef397de5e41ec1156cf3f5930893cbd7ab4c9
rests_on: [PLAN1]
record: README.md
---

# cruise can now check a package and say what makes it hard to use.

## How it works now

Run `cruise diagnose <package-folder>` and it lists every problem it finds, grouped by whether a reader can find and cite the data, understand each column, and trust the values. Each problem names the column and the rows that show it, and suggests a fix. It ends with a completeness score and says whether anything blocks publishing; only missing required fields and structure errors block, so legacy data with gaps can still be published with the gaps shown. `cruise audit <folder>` runs the same checks over every package in a folder and ranks them by what needs fixing. Both work offline, change nothing, and give `--json` for other tools. The rules live in `cruise.rules`, so the archive's submission pipeline and the agent tools can run the same checks later.

## Results

- 14 quality rules, `cruise diagnose` and `cruise audit`, with the contract's evidence row count and completeness score: PLAN1, research-in-a-box#9
- Plan 3's spec, plan and cross-plan Decision log lines on main for the other plans: PLAN1, research-in-a-box#6
- A small messy test package with each value problem planted once, and the real output of every sign-off run in `documents/cruise-runs-4f023dd.txt`: PLAN1, research-in-a-box#9

## Different from the plan

The scope was cut during planning, at your word, to the rules, diagnose and audit; tidy, package, inventory and profile are follow-ups to plan once diagnose has been used. Ozone was checked only on paper, since its hand-made package uses a draft of the format the contract can't read; a real run waits on Plan 5. The final review added a `values.unreadable` note so a table that can't be read is never skipped silently. Task 5 was added at sign-off to record the runs' output after you asked to see it.
