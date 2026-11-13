# Planted problems in the messy package

Each problem is planted once, so `cruise diagnose --profile ecology` must give exactly the
findings below: one per row of the table by rule and target, and no others. Rows are 1-based
data rows of `data/observations.csv`. A target of `package` is the manifest itself.

| Planted problem                                         | Rule                              | Target                      |
| ------------------------------------------------------- | --------------------------------- | --------------------------- |
| No license and no rights status                         | `package.core-missing`            | `package`                   |
| No `archive:methods`, which ecology requires            | `package.profile-field-missing`   | `package`                   |
| `canopy_cover` is a ratio with no unit                  | `field.unit-missing`              | `observations.canopy_cover` |
| `n/a` in the integer column `fish_count` (row 26)       | `values.not-declared-type`        | `observations.fish_count`   |
| `-999` in the number column `depth_m` (row 12)          | `values.placeholder`              | `observations.depth_m`      |
| `entered` holds `06/18/2023` among ISO dates (row 18)   | `values.mixed-date-formats`       | `observations.entered`      |
| `date` is 2017-12-15, before the coverage start (row 1) | `values.dates-outside-coverage`   | `observations.date`         |
| No rows in 2020, inside the coverage                    | `values.coverage-gap`             | `observations.date`         |
| Latitude and longitude swapped (row 21)                 | `values.coordinates-out-of-range` | `observations.latitude`     |
| A latitude of 95 (row 30)                               | `values.coordinates-out-of-range` | `observations.latitude`     |
| `obs_id` 39 repeated (rows 39 and 40)                   | `values.duplicate-key`            | `observations.obs_id`       |

The swapped row and the latitude of 95 share one finding: a rule reports at most one finding
per column, and a row that looks swapped is reported on the latitude column only.

`_build/make.py` writes the package; rerunning it leaves `git diff` empty.
