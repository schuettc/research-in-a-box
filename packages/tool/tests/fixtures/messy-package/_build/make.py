"""Build the messy test package from fixed, invented data.

Every byte is fixed: no timestamps and no randomness, so rerunning this script leaves
`git diff` empty. The package is structurally valid; its value problems are planted once each
and listed, with the rule each must trigger, in `_build/GAPS.md`.

Usage: uv run python packages/tool/tests/fixtures/messy-package/_build/make.py
"""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from archive_contract.manifest import Manifest
from archive_contract.validate import CHECKSUMS, MANIFEST, package_files

ROOT = Path(__file__).resolve().parents[1]
ROWS = 40
YEARS = (2018, 2019, 2021, 2022)
"""The years with rows: 2020, inside the coverage, has none."""

SITE_CODES = [
    ("NR1", "North Run, lower pool", "The pool below the North Run footbridge."),
    ("NR2", "North Run, upper riffle", "The riffle above the North Run footbridge."),
    ("SR1", "South Run, beaver dam", "The pond behind the South Run beaver dam."),
]

# The planted problems, by 0-based row index.
EARLY_DATE_ROW = 0
PLACEHOLDER_ROW = 11
SLASH_DATE_ROW = 17
SWAPPED_ROW = 20
WRONG_TYPE_ROW = 25
LATITUDE_95_ROW = 29


# --- JSON, written the way prettier formats it -------------------------------------------


def _scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def to_json(value: Any, indent: int = 0, prefix_width: int = 0, trailing: int = 0) -> str:
    """JSON with objects always expanded and scalar arrays on one line when they fit in 80
    columns, which is what prettier leaves unchanged."""
    pad = " " * indent
    inner = " " * (indent + 2)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = list(value.items())
        lines = []
        for i, (key, item) in enumerate(items):
            last = i == len(items) - 1
            head = f"{_scalar(key)}: "
            body = to_json(item, indent + 2, indent + 2 + len(head), 0 if last else 1)
            lines.append(f"{inner}{head}{body}{'' if last else ','}")
        return "{\n" + "\n".join(lines) + f"\n{pad}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        if all(not isinstance(v, dict | list) for v in value):
            flat = "[" + ", ".join(_scalar(v) for v in value) + "]"
            if prefix_width + len(flat) + trailing <= 80:
                return flat
        lines = []
        for i, item in enumerate(value):
            last = i == len(value) - 1
            body = to_json(item, indent + 2, indent + 2, 0 if last else 1)
            lines.append(f"{inner}{body}{'' if last else ','}")
        return "[\n" + "\n".join(lines) + f"\n{pad}]"
    return _scalar(value)


# --- Files ----------------------------------------------------------------------------------


def write(relative: str, data: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8"))


def file_meta(relative: str) -> dict[str, Any]:
    data = (ROOT / relative).read_bytes()
    return {"bytes": len(data), "hash": "sha256:" + hashlib.sha256(data).hexdigest()}


def csv_text(header: list[str], rows: list[list[str]]) -> str:
    return "".join(",".join(cells) + "\n" for cells in [header, *rows])


def observation(i: int) -> dict[str, str]:
    year = YEARS[(i - 1) % len(YEARS)]
    latitude = 60.9 + 0.02 * (i % 20)
    longitude = -150.2 + 0.03 * (i % 13)
    row = {
        "obs_id": str(i + 1),
        "date": f"{year}-{1 + i % 12:02d}-{1 + (i * 7) % 27:02d}",
        "entered": f"2023-{1 + i % 12:02d}-{1 + i % 27:02d}",
        "site": SITE_CODES[i % len(SITE_CODES)][0],
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "depth_m": f"{0.5 + 0.1 * (i % 15):.1f}",
        "fish_count": str((i * 3) % 17),
        "canopy_cover": f"{(i * 7) % 20 / 20:.2f}",
    }
    if i == EARLY_DATE_ROW:
        row["date"] = "2017-12-15"
    if i == PLACEHOLDER_ROW:
        row["depth_m"] = "-999"
    if i == SLASH_DATE_ROW:
        row["entered"] = "06/18/2023"
    if i == SWAPPED_ROW:
        row["latitude"], row["longitude"] = row["longitude"], row["latitude"]
    if i == WRONG_TYPE_ROW:
        row["fish_count"] = "n/a"
    if i == LATITUDE_95_ROW:
        row["latitude"] = "95.0000"
    if i == ROWS - 1:
        row["obs_id"] = str(ROWS - 1)  # the primary key of the row before
    return row


def write_tables() -> None:
    rows = [observation(i) for i in range(ROWS)]
    header = list(rows[0])
    write("data/observations.csv", csv_text(header, [[r[h] for h in header] for r in rows]))
    write(
        "data/site-codes.csv",
        csv_text(["code", "name", "description"], [list(c) for c in SITE_CODES]),
    )


# --- The manifest ---------------------------------------------------------------------------


def observations_schema() -> dict[str, Any]:
    return {
        "fields": [
            {
                "name": "obs_id",
                "type": "integer",
                "description": "The observation's number, unique to each visit.",
                "archive:measurementScale": "nominal",
            },
            {
                "name": "date",
                "type": "date",
                "description": "The day the site was visited.",
                "archive:measurementScale": "dateTime",
            },
            {
                "name": "entered",
                "type": "string",
                "description": "The day the field sheet was typed in, as written by the clerk.",
                "archive:measurementScale": "nominal",
            },
            {
                "name": "site",
                "type": "string",
                "description": "Site code, from the site code list.",
                "archive:measurementScale": "nominal",
            },
            {
                "name": "latitude",
                "type": "number",
                "description": "Where the sample was taken: degrees north, WGS 84.",
                "archive:unit": "degrees_north",
                "archive:measurementScale": "interval",
            },
            {
                "name": "longitude",
                "type": "number",
                "description": "Where the sample was taken: degrees east, WGS 84.",
                "archive:unit": "degrees_east",
                "archive:measurementScale": "interval",
            },
            {
                "name": "depth_m",
                "type": "number",
                "description": "Water depth at the sample point.",
                "archive:unit": "m",
                "archive:measurementScale": "ratio",
            },
            {
                "name": "fish_count",
                "type": "integer",
                "description": "Fish counted in a ten-minute snorkel pass.",
                "archive:unit": "fish",
                "archive:measurementScale": "ratio",
            },
            {
                "name": "canopy_cover",
                "type": "number",
                "description": "Share of the sky hidden by tree canopy above the point.",
                "archive:measurementScale": "ratio",
            },
        ],
        "primaryKey": ["obs_id"],
        "foreignKeys": [
            {"fields": ["site"], "reference": {"resource": "site-codes", "fields": ["code"]}}
        ],
    }


def resources() -> list[dict[str, Any]]:
    return [
        {
            "name": "observations",
            "path": "data/observations.csv",
            "type": "table",
            "title": "Snorkel observations",
            "description": "One row per site visit: where, when, depth, fish and canopy.",
            "format": "csv",
            "mediatype": "text/csv",
            "encoding": "utf-8",
            **file_meta("data/observations.csv"),
            "schema": observations_schema(),
            "archive:kind": "table",
        },
        {
            "name": "site-codes",
            "path": "data/site-codes.csv",
            "type": "table",
            "title": "Site codes",
            "description": "The codes used in the observations table's site column.",
            "format": "csv",
            "mediatype": "text/csv",
            "encoding": "utf-8",
            **file_meta("data/site-codes.csv"),
            "schema": {
                "fields": [
                    {
                        "name": "code",
                        "type": "string",
                        "description": "The code.",
                        "archive:measurementScale": "nominal",
                    },
                    {
                        "name": "name",
                        "type": "string",
                        "description": "The stream and spot.",
                        "archive:measurementScale": "nominal",
                    },
                    {
                        "name": "description",
                        "type": "string",
                        "description": "How to find the spot.",
                        "archive:measurementScale": "nominal",
                    },
                ],
                "primaryKey": ["code"],
            },
            "archive:kind": "table",
        },
    ]


def manifest() -> dict[str, Any]:
    raw = {
        "$schema": "https://datapackage.org/profiles/2.0/datapackage.json",
        "id": "snorkel-survey-messy",
        "name": "snorkel-survey-messy",
        "version": "1",
        "title": "Snorkel survey at three invented sites",
        "description": (
            "Fish counts, depth and canopy cover from snorkel passes at three invented sites "
            "on two streams. A test package with value problems planted for the audit; every "
            "site and count is invented."
        ),
        "keywords": ["fish", "snorkel survey", "streams"],
        "contributors": [{"title": "Cora Fictional", "roles": ["creator"]}],
        "resources": resources(),
        "archive:access": "open",
        "archive:temporalCoverage": {"start": "2018-01-01", "end": "2022-12-31"},
        "archive:spatialCoverage": {
            "bbox": [-150.5, 60.5, -149.5, 61.5],
            "description": "Three invented sites along two streams.",
        },
    }
    return Manifest.model_validate(raw).dump()


def write_checksums() -> None:
    paths, _ = package_files(ROOT)
    lines = [
        f"{hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}  {p}\n"
        for p in paths
        if p != CHECKSUMS
    ]
    write(CHECKSUMS, "".join(lines))


def main() -> None:
    shutil.rmtree(ROOT / "data", ignore_errors=True)
    write_tables()
    write(MANIFEST, to_json(manifest()) + "\n")
    write_checksums()


if __name__ == "__main__":
    main()
