# Stream temperature at three invented sites

Hourly water temperature from loggers at three invented stream sites, with each logger's condition, the site locations, a depth grid and the methods. A sample package for the research archive; every site and reading is invented.

This README is generated from `datapackage.json`. Edit the manifest, not this file.

## Citation

Ada Invented. Stream temperature at three invented sites. Version 1. `stream-temperature-sample`.

## Creators

- Ada Invented

## Rights

- Licensed CC-BY-4.0 (Creative Commons Attribution 4.0 International): <https://creativecommons.org/licenses/by/4.0/>

## About

- **Access:** open
- **Keywords:** stream temperature, water quality, loggers
- **Temporal coverage:** 2024-06-01 to ongoing
- **Spatial coverage:** west -72.74, south 44.23, east -72.66, north 44.32. Three invented sites along two streams.

## Resources

### `logger`: Logger readings

Kind: table. File: `data/logger.csv`.

Hourly water temperature at three sites on 1 June 2024.

| Column         | Title                 | Type     | Description                                                | Codes             |
| -------------- | --------------------- | -------- | ---------------------------------------------------------- | ----------------- |
| `timestamp`    | Reading time          | datetime | Local standard time of the reading, on the hour.           |                   |
| `site`         | Site                  | string   | Site code; the sites resource holds each site's location.  |                   |
| `water_temp_c` | Water temperature (C) | number   | Water temperature in degrees Celsius.                      |                   |
| `condition`    | Logger condition      | string   | The logger's condition at the reading, from the code list. | `condition-codes` |
| `qc_flag`      | QC flag               | string   | Quality flag set by the logger's software.                 | undocumented      |
| `logger_model` | Logger model          | string   | Model of the temperature logger.                           |                   |
| `battery_v`    |                       | number   |                                                            |                   |
| `depth_cm`     |                       | integer  | depth_cm                                                   |                   |

### `condition-codes`: Logger condition codes

Kind: table. File: `data/codes/condition-codes.csv`.

The codes used in the logger table's condition column.

| Column        | Title | Type   | Description          | Codes |
| ------------- | ----- | ------ | -------------------- | ----- |
| `code`        |       | string | The code.            |       |
| `label`       |       | string | A short label.       |       |
| `description` |       | string | What the code means. |       |

### `sites`: Sites

Kind: vector. File: `data/sites/sites.shp`.

The three logger sites as points, in WGS 84.

With `data/sites/sites.shx`, `data/sites/sites.dbf`, `data/sites/sites.prj`.

### `depth`: Stream depth

Kind: raster. File: `data/depth.asc`.

Stream depth in centimetres on a coarse grid, as an ESRI ASCII grid.

With `data/depth.prj`.

### `logger-xlsx`: Logger readings (Excel)

Kind: table. File: `data/logger.xlsx`. The same data as `logger`, in another format.

The logger table as an Excel workbook.

### `logger-original`: Logger export, untouched

Kind: file. File: `original/logger-raw.csv`.

The logger software's export before cleaning.

### `methods`: Methods

Kind: document. File: `docs/methods.md`.

How the loggers were placed, read and checked.

### `site-photo`: Site photo

Kind: media. File: `docs/site-photo.png`.

A stand-in picture of site S1.

### `discharge`: Discharge

Kind: linked. Held at <https://example.org/stream-temperature/discharge.csv>.

Stream discharge at the same sites, held by a partner program.
