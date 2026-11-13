# The FEMC paper test

Each of FEMC's six practice datasets, written down in the package format on paper: the
resources it becomes and their kinds, how its rights are stated, its code lists, its legacy
identifiers, its project, and what `from_eml` reads from its EML record and what it skips. The
list at the end names what the format can't express, each with the dataset that showed it.

**Sources.** The records and files in `practice-data/femc/` of the main clone, fetched from the
FEMC Data Archive on 2026-11-12 (its `SOURCES.md` gives the pages and the license each page
shows). Nothing from `practice-data/` is committed: this document describes FEMC's public
metadata and the shape of the files only. `from_eml` was run on each `eml.xml` at commit
`a204e7a` with a throwaway script kept outside the repo. Where a record or file is silent, this
document says so rather than guessing.

## What every record has in common

All six records are EML 2.1.1 (`eml://ecoinformatics.org/eml-2.1.1`) written by FEMC's system
`vmc`, and they share one non-standard shape:

- Every element carries the `eml:` prefix. Standard EML leaves the children unqualified.
  `from_eml` matches elements by local name, so this alone costs nothing.
- The dataset has no `title`, `creator`, `abstract`, `keywordSet`, `intellectualRights`,
  `coverage` or `contact`. The title, description, purpose and coverage sit on the single
  `dataTable` instead, as `title`, `description`, `purpose` and `coverage`. Standard EML names
  an entity with `entityName` and describes it with `entityDescription`.
- `publisher` wraps a `metadataProvider` (FEMC itself, with its address); standard EML puts the
  party's fields directly inside `publisher`.
- Project `personnel` holds role-named elements (`principalInvestigator`, `contentProvider`)
  with `surName` and `givenName` inside, instead of `individualName` plus `role`. The project
  also carries `shortName` (always equal to its title) and, in four records, a `keywordSet`.
- `physical` holds `objectName` (FEMC's internal id, such as `VMC.23.214`, not a file name),
  `dataFormat/formatName` (always `mySQL`, with no `externallyDefinedFormat` around it), a
  `citation` with FEMC's preferred citation, and `distibution` (misspelled) with the dataset's
  FEMC page URL.
- Each attribute has `measurementType` where standard EML has `measurementScale`, and inside
  it the scale element is empty: no units, no number types, no domains. Only `datetime` carries
  a `formatString`.

So for every record `from_eml` reads only:

- the `packageId`, as `archive:legacyIdentifiers` `{scheme: "eml-package-id"}`;
- the project's `title` and `abstract`, as a `Project` named by `archive:project`;
- any dataset-level `associatedParty`, as contributors with its role.

It reads no title, description, creators, keywords, rights, coverage, methods, resources,
fields or code lists, because none sit where standard EML puts them. The `dataTable` has no
`entityName`, so it becomes no resource; `from_eml` still walks it to list what it skipped. The
misspelled `distibution` is listed as skipped (`not standard EML`); it is not handled here.
Tolerating these records is Plan 5's.

The skip lines every record shares:

```
dataset/publisher: not read
dataset/project/shortName: not standard EML
dataset/project/personnel: no name, so no person
dataset/dataTable/title: not standard EML
dataset/dataTable/coverage: not read
dataset/dataTable/description: not standard EML
dataset/dataTable/purpose: not standard EML
dataset/dataTable/shortName: not standard EML
dataset/dataTable: no entityName, so no resource
dataset/dataTable/physical/citation: not standard EML
dataset/dataTable/physical/distibution: not standard EML
dataset/dataTable/physical/dataFormat/formatName: not standard EML
```

Each dataset below lists only its extra skip lines.

In every package written below, the untouched download goes under `original/` as a `file`
resource and the tidy copy of a table under `data/`, as the format lays out. Rights are not in
any EML record; they come from the license FEMC's dataset page shows, as recorded in
`SOURCES.md`. No record has a geographic coverage, so no package below has
`archive:spatialCoverage`.

## Ozone Bioindicators (`ozone-bioindicators`)

**Resources.**

| Resource       | Kind  | From                                                          |
| -------------- | ----- | ------------------------------------------------------------- |
| `ozone`        | table | `Z0023_ozone.csv`: 165 rows, 17 columns                       |
| `ozone-source` | file  | the same download, untouched, under `original/`               |

The 17 EML attributes match the CSV's 17 column names exactly, in a different order. Four
attributes (`ID`, `PROJECT`, `HEXAGONNUMBER`, `PLOTNUMBER`) have no definition, storage type
or measurement type. Several definitions only repeat the name (`SPECIES`, `YEAR`,
`SEVERITY_MINIMUM`).

**Title, description, coverage, creators.** Title from the `dataTable` title, "Ozone
Bioindicators". Description from the `dataTable` description, "Ozone sensitive plant species
evaluated for injury" (exactly 50 characters, the core minimum). Temporal coverage 1997-01-01
to 2001-12-31. The record names no creator; FEMC's citation names J. Lackey and S. Wilmot.

**Rights.** FEMC shows "Linked - third party determines data license". That is
`archive:rightsStatus: third-party` with FEMC's words as the statement. The format wants the
statement to say where the terms are set; FEMC doesn't say which third party (the citation
credits VT Forests, Parks & Recreation, but not as the licensor).

**Code lists.** None in the record. `SPECIES` holds numbers (`365`, `541`) and is defined only
as "SPECIES", so it is `archive:codeList: "undocumented"`. Whether `ID` (values like `D`) and
`PROJECT` (`1`) are codes the record doesn't say.

**Legacy identifiers.** `eml-package-id` `vmc.23.214.1`; FEMC's object name `VMC.23.214`
(a scheme such as `femc-object`). The file name's `Z0023` repeats the dataset number.

**Project.** `project.json` "Ozone Bioindicator Plant Monitoring" with its abstract and five
people: three `contentProvider`, two `principalInvestigator`, as `Person.roles`. Its keywords
(plant species, monitoring, ozone, bioindicator) have no place in the project record.

**from_eml.** Reads the package id and the project title and abstract. Extra skips:

```
dataset/project/keywordSet: not standard EML
dataset/project/personnel/contentProvider: not standard EML (3 times)
dataset/project/personnel/principalInvestigator: not standard EML (2 times)
dataset/dataTable/attributeList/attribute/measurementType: not standard EML (13 times)
```

## Tree-level FIA data (`fia-tree-level`)

**Resources.**

| Resource   | Kind  | From                                                          |
| ---------- | ----- | ------------------------------------------------------------- |
| `fia-tree` | table | `Z0311_FIA_TREE_1983_2015.csv`: 162,354 rows, 207 columns     |
| source     | file  | the same download, untouched, under `original/`               |

The record describes 158 attributes; all 158 are CSV columns, and 49 CSV columns have no
attribute (`ACTUALHT_CALC`, `AGENTCD_NERS`, `CULL_BF_ROTTEN` and others). Those 49 get fields
with a type and no description. `CREATED_BY` and `MODIFIED_BY` may hold people's names; the
record doesn't say, so `archive:sensitivity: personal` is a call for whoever converts it.

**Title, description, coverage, creators.** Title and description from the `dataTable`. The
temporal coverage is a `rangeOfDates` with a begin date (1983-01-01) and no end date, which
standard EML doesn't allow. The citation says "Ongoing" and the file name says 1983 to 2015.
The format needs an end date or `ongoing`; the record gives neither (see the list below). No
creator element; the citation's author is the US Forest Service.

**Rights.** "Linked - third party determines data license": `third-party`. The citation points
to the FIA DataMart (`https://apps.fs.usda.gov/fia/datamart/`), the nearest the record comes to
saying where the terms are set.

**Code lists.** None in the record. Many columns are coded and defined only by name, such as
`AGENTCD` ("Agent code"), so they are `undocumented`. The FIA codes are published in the FIA
database manual, outside the record; a converter could add them as code-list tables.

**Legacy identifiers.** `eml-package-id` `vmc.311.300.1`; object name `VMC.311.300`.

**Project.** "Federal Forest Inventory and Analysis Data for Vermont", with its abstract, one
`principalInvestigator` (Randall Morin) and four project keywords.

**from_eml.** Reads the package id and the project. Extra skips:

```
dataset/project/keywordSet: not standard EML
dataset/project/personnel/principalInvestigator: not standard EML
dataset/dataTable/attributeList/attribute/measurementType: not standard EML (149 times)
```

## Fine Aerosol Monitoring: IMPROVE 1991-2001 (`improve-fine-aerosol`)

**Resources.**

| Resource  | Kind  | From                                                          |
| --------- | ----- | ------------------------------------------------------------- |
| `improve` | table | `Z0100_LYBR1.csv`: 971 rows, 239 columns                      |
| source    | file  | the same download, untouched, under `original/`               |

The 239 attributes match the 239 columns by name, in a different order. Most columns come in
fours per analyte: `AL_val`, `AL_unc`, `AL_mdl`, `AL_flag` (value, uncertainty, detection
limit, flag). Most definitions repeat the name. `obs_date` is `DD/MM/YYYY` (Frictionless
`format: "%d/%m/%Y"`); `obs_time` holds values like `12:00:00 AM` (`format: "%I:%M:%S %p"`).

**Title, description, coverage, creators.** Title and description (94 characters) from the
`dataTable`. Temporal coverage 1991-09-21 to 2001-11-27. No creator element; the citation names
R. Lacaillade, R. Perron and B. Whitney.

**Rights.** "Linked - third party determines data license": `third-party`, with no third party
named.

**Code lists.** None in the record. The `_flag` columns hold codes (`NM`) and are
`undocumented`.

**Legacy identifiers.** `eml-package-id` `vmc.100.221.1`; object name `VMC.100.221`.

**Project.** "Fine Particle Monitoring: Interagency Monitoring of Protected Visual Environments
(IMPROVE)", with its abstract, three `principalInvestigator` and three `contentProvider`, and
five project keywords.

**from_eml.** Reads the package id and the project. Extra skips:

```
dataset/project/keywordSet: not standard EML
dataset/project/personnel/principalInvestigator: not standard EML (3 times)
dataset/project/personnel/contentProvider: not standard EML (3 times)
dataset/dataTable/attributeList/attribute/measurementType: not standard EML (238 times)
```

## Regional Aerial Detection Survey (`aerial-detection-survey`)

**Resources.** The download is one zip of ten files:

| Resource              | Kind   | From                                                                       |
| --------------------- | ------ | -------------------------------------------------------------------------- |
| `aerial-survey`       | vector | the `.shp`, with `.shx`, `.dbf`, `.prj`, `.cpg`, `.sbn`, `.sbx`, `.shp.xml` |
| `aerial-survey-table` | table  | the `.csv`: the shapefile's attribute table, 42 columns, no geometry        |
| `aerial-survey-xlsx`  | table  | the `.xlsx`, with `archive:alternateOf: aerial-survey-table`                |
| source                | file   | the zip, untouched, under `original/`                                      |

The eight shapefile parts are one resource with `archive:files`; `.shp.xml` is ESRI's own
metadata file and `.sbn`/`.sbx` a spatial index, kept as members. The CSV is the attribute
table of the shapefile, not the same data (it has no geometry), so it is its own table rather
than an alternate of the vector (see the list below). The record's 27 attributes describe the
CSV only in part: 24 match a column, `State`, `Area_ha` and `Shape_Length` match `STATE`,
`Area_Ha` and `Shape_Leng` only after a case change or the shapefile's 10-character limit
(each becomes `archive:sourceName` or a rename in `changes.jsonl`), and 15 columns have no
attribute (`HOST4`, `PATTERN1`, `TPA1`, `NOTES`, `SURVEY_ID1` and others).

**Title, description, coverage, creators.** Title and description from the `dataTable`; its
purpose ("Monitoring forest condition in the states of NY, VT, NH, ME, CT, RI and MA") has no
field of its own. Temporal coverage 1918-01-01 to 2018-04-30, though the file name says 1918
to 2019. No creator element; the citation's authors are FEMC and the Northeastern States
Research Cooperative.

**Rights.** FEMC's page shows no license: `archive:rightsStatus: undetermined`. The package can
be built and audited; it can't be published until someone states the rights.

**Code lists.** The only record of the six with code lists. Its `enumeratedDomain` sits directly
in the attribute (not standard), with `codeDefinition`s:

- one 12-code list for damage type, repeated on `DMG_TYPE1`, `DMG_TYPE2` and `DMG_TYPE3`: one
  table `data/codes/damage-type.csv` with three foreign keys;
- one 3-code list for defoliation severity, on `SEVERITY1` to `SEVERITY3`: one table, three
  foreign keys.

Both lists include `-1` "No data", a code that means a missing value; it stays a row of the
code list. `State` has an empty `enumeratedDomain`. `DCA1-3`, `HOST1-3`, `FOR_TYPE1-3` and
`NO_TREES1-3` are federal codes with no list: `undocumented`.

**Legacy identifiers.** `eml-package-id` `vmc.1216.2428.1`; object name `VMC.1216.2428`; the
zip's name also carries an export timestamp (`20210315134757`).

**Project.** "Northeastern Regional Aerial Detection Surveys and Insect and Disease Surveys",
its abstract, ten personnel (four `principalInvestigator`, six `contentProvider`) and six
project keywords. Three dataset-level associated parties: the USDA Forest Service (`funder`,
also an `archive:funding` funder), the Northeastern States Research Cooperative (`lead`) and
FEMC (`partner`).

**from_eml.** Reads the package id, the project, and the three associated parties as
contributors with those roles. Extra skips:

```
dataset/project/keywordSet: not standard EML
dataset/project/personnel/contentProvider: not standard EML (6 times)
dataset/project/personnel/principalInvestigator: not standard EML (4 times)
dataset/dataTable/attributeList/attribute/measurementType: not standard EML (27 times)
dataset/dataTable/attributeList/attribute/enumeratedDomain: not standard EML (7 times)
```

## Data Rescue Inventory (`data-rescue-inventory`)

**Resources.**

| Resource         | Kind  | From                                                          |
| ---------------- | ----- | ------------------------------------------------------------- |
| `rescue-inventory` | table | `Z1379_2933_BWS7LK.csv`: 338 rows, 50 columns               |
| source           | file  | the same download, untouched, under `original/`               |

All 50 columns have an attribute, and the record lists 25 more that aren't in the file
(`AboutP1` to `AboutP6`, `HomeP1`, `HomeP2`, `Documentation` and others, apparently web page
text). Those 25 have no column to describe. `Contact` and `ContactEmail` hold people's names
and email addresses: `archive:sensitivity: personal`. `Lat1` and `Long1` are locations; whether
they are sensitive the record doesn't say.

**Title, description, coverage, creators.** Title "Data Rescue Inventory". The `dataTable`
description is "data rescue inventory", 21 characters, short of the 50 the core fields need;
the project abstract is long enough but the format never copies a project's text into a
package, so someone has to write the description. The coverage is a `rangeOfDates` with only a
begin date, 2019-03-11, and no end or ongoing statement. No creator element and no citation.

**Rights.** No license shown: `undetermined`.

**Code lists.** None. The state columns (`CT`, `ME`, `MA` ...) and theme columns (`Forest`,
`Water` ...) look like flags; the record doesn't define their values.

**Legacy identifiers.** `eml-package-id` `vmc.1379.2933.1`; object name `VMC.1379.2933`; the
file name adds `BWS7LK`, whose meaning the record doesn't give.

**Project.** "Data Rescue Project", its abstract, and an empty `personnel`. One associated
party, FEMC (`lead`).

**from_eml.** Reads the package id, the project and the associated party. Extra skips:

```
dataset/dataTable/attributeList/attribute/measurementType: not standard EML (59 times)
```

## Camels Hump census_data (`camels-hump-census`)

**Resources.** No data file: FEMC holds only the record.

| Resource      | Kind   | From                                                                                    |
| ------------- | ------ | --------------------------------------------------------------------------------------- |
| `census-data` | linked | `https://github.com/stephenrkeller/CamelsHump_forestInventoryPlots/tree/main/data/census_data` |

The URL comes from the `citation` text ("Available online at: ..."), not from a standard
element; `distibution` holds FEMC's page instead. It points at a folder of a repository, not a
file, so the resource has no `format`. The `attributeList` is empty, so there is no schema.

**Title, description, coverage, creators.** Title "census_data". The description, "Github repo
of census_data" (26 characters), is short of the core 50. Coverage is a `rangeOfDates` with only
a begin date, 1965-01-01; the project abstract says censuses continue every five years, which
reads as ongoing, but the record itself doesn't say so. No creator element; the citation names
S. Keller.

**Rights.** "Linked - third party determines data license": `third-party`. The terms would be
the GitHub repository's; this paper test didn't fetch it to check.

**Code lists.** None.

**Legacy identifiers.** `eml-package-id` `vmc.1872.4112.1`; object name `VMC.1872.4112`.

**Project.** "Camels Hump Forest Inventory Plots", its abstract and an empty `personnel`. One
associated party, the University of Vermont (`lead`).

**from_eml.** Reads the package id, the project and the associated party. No extra skips: the
record has no attributes.

## What the format can't express

Each item is something one of these datasets holds that has no place in the format. None of
them changes the contract here; each is for the user to decide.

1. **A start date with no known end.** The format's temporal coverage needs an end date or
   `ongoing`. `fia-tree-level` (begins 1983, the citation says "Ongoing", the file stops at
   2015), `camels-hump-census` (begins 1965; the project says censuses continue) and
   `data-rescue-inventory` (begins 2019-03-11, nothing more) give only a start. Writing them
   down means asserting `ongoing` or inventing an end.
2. **Units of measure.** A column has a logical type and no unit. `fia-tree-level` says
   `ACTUALHT` is to "the nearest foot" only in prose; `improve-fine-aerosol`'s concentrations
   and uncertainties have no units anywhere. The EML export has to write the custom unit
   `unknown` because EML requires one.
3. **How columns relate to each other.** `improve-fine-aerosol` has, per analyte, a value, its
   uncertainty, its detection limit and its flag (`AL_val`, `AL_unc`, `AL_mdl`, `AL_flag`).
   The format can say a column uses a code list, not that one column is the uncertainty or the
   flag of another.
4. **Measurement scale.** The format has logical types only, so it can't say a coded integer is
   ordinal rather than nominal (`fia-tree-level`'s `DAMSEV1`, "Damage Severity", is
   `ordinal`), or a number interval rather than ratio (`BHAGE`, `Area_ha` in
   `aerial-detection-survey`).
5. **A table that is part of another resource.** `aerial-detection-survey`'s CSV is the
   shapefile's attribute table without the geometry. `archive:alternateOf` means the same data
   in another format, which this isn't; the format has no way to say "the attribute table of
   `aerial-survey`".
6. **The source's preferred citation.** Five records carry FEMC's preferred citation (such as
   "Lackey, J., and S. Wilmot. 2001. Ozone Bioindicators. ..."). The README generates a
   citation from the manifest; there is no field to keep the citation the source asked for.
7. **Project keywords.** Four projects (`ozone-bioindicators`, `fia-tree-level`,
   `improve-fine-aerosol`, `aerial-detection-survey`) carry keywords. The project record has
   `id`, `title`, `abstract`, `people` and `links`, and no keywords; the format would only allow
   copying them onto each package, which the spec avoids for project text.
8. **A purpose separate from the description.** Every `dataTable` but two empty ones has a
   `purpose` (`aerial-detection-survey`: "Monitoring forest condition in the states of ...").
   The format has `description` and `archive:methods` only; a purpose has to be folded into
   the description.

## Found on the way, not format gaps

These are things the format can hold, or findings about FEMC's records for the audit (Plan 3)
and the converter (Plan 5):

- No record states rights, creators, keywords or geographic coverage in EML; rights come only
  from FEMC's web page, and two datasets (`aerial-detection-survey`, `data-rescue-inventory`)
  show none, so they stay `undetermined`.
- The EML and the file disagree: `data-rescue-inventory` documents 25 columns the file
  doesn't have, `fia-tree-level` leaves 49 columns undocumented, and
  `aerial-detection-survey` documents 27 of 42 columns with three names in a different case or
  truncated.
- Coverage disagrees with file names (`aerial-detection-survey`: 2018-04-30 in the record,
  2019 in the zip's name; `fia-tree-level`: ongoing in the citation, 2015 in the file name).
- Two descriptions are shorter than the core 50 characters (`data-rescue-inventory`,
  `camels-hump-census`), and many column definitions only repeat the column name.
- The FEMC landing page in `distibution` fits Frictionless `homepage` or a related identifier
  of type URL; FEMC's object names (`VMC.23.214`) fit `archive:legacyIdentifiers`; shared
  code lists (`aerial-detection-survey`'s `DMG_TYPE1-3`) fit one code-list table with several
  foreign keys; personal columns (`data-rescue-inventory`'s `ContactEmail`) fit
  `archive:sensitivity`.
