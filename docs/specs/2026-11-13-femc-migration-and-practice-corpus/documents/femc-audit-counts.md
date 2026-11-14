# FEMC practice corpus: audit counts

Counts from `cruise audit --config examples/femc/archive.yaml --json` over the ten converted packages, run on 2026-11-14 with the `femc` converter at commit 4c720b3 (branch plan5/femc-converter) and cruise at 9a74bc7 (main). Only counts and rule ids are here: the full output, whose findings quote data values, stays under `practice-data/audit/` and is not committed.

Errors block publishing; warnings and notes never do. The score is cruise's unweighted completeness score (0 to 100); find, understand and trust are the checks passed out of those that apply.

| # | Dataset | Errors | Warnings | Notes | Score | Find | Understand | Trust |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ozone-bioindicators | 3 | 24 | 1 | 76 | 5 of 8 | 40 of 61 | 46 of 50 |
| 2 | data-rescue-inventory | 5 | 68 | 0 | 69 | 3 of 8 | 50 of 116 | 114 of 116 |
| 3 | improve-fine-aerosol | 3 | 640 | 1 | 58 | 5 of 8 | 476 of 881 | 423 of 659 |
| 4 | camels-hump-census | 4 | 0 | 0 | 50 | 4 of 8 | 0 of 0 | 0 of 0 |
| 5 | aerial-detection-survey | 4 | 101 | 1 | 76 | 4 of 8 | 209 of 279 | 132 of 164 |
| 6 | fia-tree-level | 3 | 185 | 3 | 85 | 5 of 8 | 482 of 665 | 605 of 610 |
| 7 | vegetation-class-raster | 3 | 0 | 0 | 62 | 5 of 8 | 0 of 0 | 0 of 0 |
| 8 | mount-mansfield-quadrat-images | 4 | 0 | 0 | 50 | 4 of 8 | 0 of 0 | 0 of 0 |
| 9 | development-related-te-species | 4 | 0 | 0 | 50 | 4 of 8 | 0 of 0 | 0 of 0 |
| 10 | white-clover-biomonitor | 4 | 0 | 0 | 50 | 4 of 8 | 0 of 0 | 0 of 0 |

## Rules that fired, per dataset

**ozone-bioindicators**: `field.unit-missing` (warning) ×14, `field.description-missing` (warning) ×4, `field.description-repeats-name` (warning) ×3, `values.constant` (warning) ×3, `package.profile-field-missing` (error) ×2, `package.core-missing` (error) ×1, `values.coverage-gap` (note) ×1

**data-rescue-inventory**: `field.description-missing` (warning) ×50, `field.unit-missing` (warning) ×16, `package.core-missing` (error) ×3, `package.profile-field-missing` (error) ×2, `values.constant` (warning) ×2

**improve-fine-aerosol**: `field.description-repeats-name` (warning) ×237, `values.placeholder` (warning) ×173, `field.unit-missing` (warning) ×166, `values.constant` (warning) ×59, `values.not-declared-type` (warning) ×3, `field.description-missing` (warning) ×2, `package.profile-field-missing` (error) ×2, `package.core-missing` (error) ×1, `values.coverage-gap` (note) ×1

**camels-hump-census**: `package.core-missing` (error) ×2, `package.profile-field-missing` (error) ×2

**aerial-detection-survey**: `field.description-missing` (warning) ×47, `values.placeholder` (warning) ×30, `field.unit-missing` (warning) ×23, `package.core-missing` (error) ×2, `package.profile-field-missing` (error) ×2, `values.coverage-gap` (note) ×1, `values.not-declared-type` (warning) ×1

**fia-tree-level**: `field.unit-missing` (warning) ×109, `field.description-missing` (warning) ×65, `field.description-repeats-name` (warning) ×9, `values.coverage-gap` (note) ×3, `package.profile-field-missing` (error) ×2, `values.constant` (warning) ×2, `package.core-missing` (error) ×1

**vegetation-class-raster**: `package.profile-field-missing` (error) ×2, `package.core-missing` (error) ×1

**mount-mansfield-quadrat-images**: `package.core-missing` (error) ×2, `package.profile-field-missing` (error) ×2

**development-related-te-species**: `package.core-missing` (error) ×2, `package.profile-field-missing` (error) ×2

**white-clover-biomonitor**: `package.core-missing` (error) ×2, `package.profile-field-missing` (error) ×2

## Across the ten

| Rule | Times fired |
| --- | --- |
| `field.unit-missing` | 328 |
| `field.description-repeats-name` | 249 |
| `values.placeholder` | 203 |
| `field.description-missing` | 168 |
| `values.constant` | 66 |
| `package.profile-field-missing` | 20 |
| `package.core-missing` | 17 |
| `values.coverage-gap` | 6 |
| `values.not-declared-type` | 4 |
