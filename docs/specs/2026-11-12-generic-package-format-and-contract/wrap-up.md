---
diazo: research-archive-in-a-box/generic-package-format-and-contract
file: wrap-up
status: printed
hash: 78715205d00700610fdbe6d668fc765a566b7935831811228401247265c12292
rests_on: [PLAN1, PLAN2, PLAN3]
record: README.md
---

# research-in-a-box now has a working package format: a Python contract that describes, validates and exports a dataset package, with a sample package to test against.

## How it works now

A dataset package is a plain folder that is also a valid Frictionless Data Package, and `archive_contract` reads it into typed models, checks its structure (references, member files, checksums, hashes, symlinks), and exports it as a README, DataCite, schema.org and EML 2.2.0. It can also read standard EML in. The format holds what research data actually carries: rights statuses beside licenses, code lists as small tables, shapefile sets as one resource, projects as their own record, units, measurement scales, related columns, preferred citations and coverage that is ongoing or has no known end. The committed sample package, an invented stream temperature study, uses all of it and rebuilds byte for byte, and FEMC's six practice datasets have been written down in the format as a test. Plans 3 to 9 can now build on the contract.

## Results

- Models, structural validation, the generated JSON Schema and the sample package: PLAN1, research-in-a-box#1.
- README, DataCite, schema.org and EML exports, EML import and the FEMC paper test: PLAN2, research-in-a-box#3.
- The eight fields the paper test found missing: PLAN3, research-in-a-box#4.

## Different from the plan

PLAN3 was added after the paper test found eight things the format couldn't hold, and you chose to add all of them. The DataCite export is checked against DataCite's mandatory properties instead of a vendored JSON Schema, because the only one available is unofficial and has no licence. Plan 3 confirms the change log and findings shapes when it starts, rather than before the spec was printed, since it hadn't begun.
